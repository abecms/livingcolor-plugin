# LivingColor GitHub VCS Provider Design

## Goal

Add GitHub support to LivingColor so a project hosted on GitHub works the same way an existing GitLab-backed project works today: users can connect credentials, choose a repository, run readiness and delivery flows, let agents work in a managed checkout, and publish the approved delivery branch as a GitHub Pull Request.

The delivery workflow remains unchanged at the product level:

1. Jira readiness scan.
2. Human promotion to a Work Order.
3. Analysis, development, and review gates.
4. Publisher agent pushes the approved branch.
5. LivingColor creates and verifies a provider-specific review request.

GitHub.com is the only officially supported GitHub host in this first version. The design keeps provider boundaries clear enough to add GitHub Enterprise later without rewriting the flow.

## Non-Goals

- Support GitHub Enterprise in the first version.
- Replace Jira as the source of readiness tickets.
- Change the gate sequence or Work Order lifecycle.
- Rename all existing `merge_request` gate types in storage.
- Require GitHub for existing GitLab projects.
- Let agents publish through direct REST calls, `curl`, or ad hoc scripts.

## Provider Selection

Each project gets an explicit VCS provider setting:

```yaml
MYPROJ:
  vcs: github
  default_repo: github.com/org/repo
  integration_branch: main
```

Supported values are `gitlab` and `github`. Missing `vcs` is treated as `gitlab` for backward compatibility with existing projects.

The explicit provider setting is the source of truth. LivingColor should not infer the provider from `default_repo`, although it may validate that a GitHub project uses a GitHub-shaped repo id and a GitLab project uses a GitLab-shaped repo id.

## Architecture

Introduce a VCS provider boundary with a small shared contract. GitLab behavior moves behind the GitLab provider; GitHub adds a sibling provider.

Recommended modules:

- `lc_server/integrations/vcs/provider.py`
- `lc_server/integrations/vcs/gitlab.py`
- `lc_server/integrations/vcs/github.py`
- `lc_server/integrations/vcs/review_request.py`

The provider contract should cover:

- Resolve project credentials from project settings and global Hermes MCP config.
- Build a redacted display status for the UI.
- List repositories accessible to the configured token.
- Build a managed clone URL.
- Resolve MCP server/toolset names for delivery agents.
- Build publisher instructions for the provider.
- Parse and verify the published review request.

GitLab remains the default provider and preserves existing behavior. GitHub implements the equivalent behavior for GitHub.com.

## Project Configuration and UI

`Project -> Integrations` gets an explicit forge selector:

- GitLab
- GitHub

When `vcs: github`, the UI shows GitHub connection controls instead of the primary GitLab controls. For the first version, it asks for a GitHub personal access token and supports GitHub.com only.

Example stored project mapping:

```yaml
MYPROJ:
  vcs: github
  default_repo: github.com/org/repo
  integration_branch: main
  integrations:
    mcp_servers:
      github:
        command: npx
        args:
          - -y
          - "@modelcontextprotocol/server-github"
        env:
          GITHUB_TOKEN: "..."
```

The repo picker lists repositories accessible to the token and saves the selected repo as `default_repo`. The V1 picker may list all accessible repositories for the token; organization filtering can be added later.

Existing GitLab project settings continue to work without a migration.

## Dynamic Prerequisites

Provisioning prerequisites become provider-aware:

- Always required: Jira MCP.
- Always required: configured Hermes delivery model.
- Required for `vcs: gitlab`: GitLab MCP credentials.
- Required for `vcs: github`: GitHub MCP credentials.

Missing prerequisite codes should be provider-specific, for example:

- `jira_mcp`
- `llm_model`
- `gitlab_mcp`
- `github_mcp`

The UI should render the missing provider prerequisite with a clear action: connect GitHub or connect GitLab for this project.

## Managed Checkout

The managed checkout flow becomes VCS-aware while preserving the existing local checkout fallback.

For GitHub:

- Repo ids are stored as `github.com/org/repo`.
- Managed checkouts remain under `~/.hermes/livingcolor/{PROJECT_KEY}/...` through the existing LivingColor home path behavior.
- Clone URLs use the token without logging it:

```text
https://x-access-token:<token>@github.com/org/repo.git
```

GitLab keeps the current OAuth2-style clone URL.

Errors must mention the active provider:

- `github_token_missing`
- `github_repo_not_found`
- `gitlab_token_missing`
- `gitlab_repo_not_found`

Any log that includes a clone URL must redact the token.

## Publisher Agent

The current GitLab-specific publisher becomes a review request publisher. It receives provider context:

```json
{
  "vcs": "github",
  "reviewRequestKind": "pull_request",
  "reviewRequestProvider": "github",
  "targetBranch": "main"
}
```

Common publisher rules:

- Commit pending delivery work deterministically before publication.
- Stay inside the Workspace Root.
- Only use `git push` as a git command.
- Never edit files, rebase, merge, or change repository contents.
- Never rewrite, summarize, or translate the approved title or description.
- Create the review request only through provider MCP tools.
- Never use `curl`, `wget`, `httpie`, `python -c`, or direct REST calls from the agent.

Provider-specific behavior:

- GitLab creates a Merge Request through GitLab MCP tools.
- GitHub creates a Pull Request through GitHub MCP tools.

The canonical completion block becomes provider-neutral:

```json
{
  "reviewRequestUrl": "https://github.com/org/repo/pull/42",
  "reviewRequestNumber": 42,
  "targetBranch": "main",
  "provider": "github",
  "status": "published"
}
```

For backward compatibility, GitLab publication can continue writing `mrUrl` and `mrIid` in places that still read them. New code should prefer `reviewRequestUrl`, `reviewRequestNumber`, and `reviewRequestProvider`.

## Verification

After publication, LivingColor verifies that the review request exists.

GitLab verification keeps the existing Merge Request verification behavior, but behind the GitLab provider.

GitHub verification calls the GitHub API for:

```text
GET https://api.github.com/repos/{owner}/{repo}/pulls/{number}
```

It uses the configured `GITHUB_TOKEN`, handles 404 as "not found", and reports provider-specific errors:

- `github_pr_not_found`
- `github_verification_failed`
- `gitlab_mr_not_found`
- `gitlab_verification_failed`

The publisher should fail the Work Order publication step if verification cannot confirm the review request.

## Data Compatibility

The storage model introduces provider-neutral review request fields:

- `reviewRequestUrl`
- `reviewRequestNumber`
- `reviewRequestProvider`

Existing fields remain readable:

- `mrUrl`
- `mrIid`

The UI displays:

- "MR" for GitLab.
- "PR" for GitHub.

Existing `merge_request` and `merge_request_review` gate types can remain in V1. Their payloads should become provider-neutral where practical.

No heavy database migration is required in V1. Use dual-read compatibility and write the new canonical fields going forward.

## Shadow Mode and Safety

Shadow mode write guards need GitHub equivalents for GitLab write tools.

GitHub write tools include, at minimum:

- `create_pull_request`
- `create_branch` / ref creation tools exposed by the MCP server
- update, merge, close, comment, or push-like GitHub MCP tools

These writes are blocked in shadow mode unless the current delivery agent role is `publisher`, matching current GitLab behavior.

Tokens must never appear in:

- logs
- UI status text
- API error details
- agent prompts
- audit payloads

## Testing

Add focused tests for:

- Project provider resolution and default `gitlab` behavior.
- Provider-aware provisioning prerequisites.
- GitHub MCP config persistence and status parsing.
- GitHub repo discovery from token-accessible repositories.
- GitHub managed clone URL generation with token redaction.
- Publisher prompt and completion parsing for GitHub.
- GitLab backward compatibility for `mrUrl` and `mrIid`.
- GitHub Pull Request verification.
- Shadow mode blocking for GitHub write tools.
- UI labels and integration state for GitHub vs GitLab.

Manual smoke test:

1. Configure a project with `vcs: github`.
2. Connect Jira and GitHub MCP credentials.
3. Select a GitHub repository in Project Integrations.
4. Run readiness scan and promote a Work Order.
5. Complete gates through publication.
6. Confirm a GitHub PR exists and the Work Order stores the provider-neutral review request fields.

## Rollout Plan

1. Add provider selection and provider resolution with default `gitlab`.
2. Extract current GitLab behaviors behind the provider boundary without changing user-facing behavior.
3. Add GitHub credentials, status, repo discovery, and managed checkout.
4. Add provider-aware prerequisites and UI.
5. Generalize publisher prompts, completion parsing, storage fields, and verification.
6. Add GitHub shadow guards and test coverage.
7. Update README and user-facing labels from GitLab-only language to provider-aware language.

## Open Constraints

- GitHub.com only in V1.
- Existing GitLab projects must keep working without editing their mapping.
- Agents must use MCP for review request creation; direct REST remains reserved for host-side verification only.
- User-facing docs and UI copy should be in English in the repository, while product runtime can continue using the existing i18n system.
