# GitHub VCS Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add GitHub.com support so LivingColor projects can use the same delivery flow as GitLab projects and publish approved work as GitHub Pull Requests.

**Architecture:** Introduce a provider-aware VCS boundary while preserving GitLab as the default. The first slices add provider resolution, GitHub credentials, discovery, clone support, and dynamic prerequisites; the following slices generalize publisher output, verification, shadow guards, UI labels, and docs.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, pytest, urllib, React 19, TypeScript, Vite/Vitest, Hermes MCP configuration.

---

## File Structure

- Create `lc_server/integrations/vcs/__init__.py`: provider package exports.
- Create `lc_server/integrations/vcs/provider.py`: provider constants, config normalization, result dataclasses, provider resolver.
- Create `lc_server/integrations/vcs/gitlab.py`: GitLab provider adapter that wraps existing GitLab discovery, clone env, toolset, and MR verification behavior.
- Create `lc_server/integrations/vcs/github.py`: GitHub.com provider adapter for token reading, repository discovery, clone URL creation, and PR verification.
- Modify `delivery_runtime/readiness/project_settings.py`: persist and load per-project `vcs`, expose provider-aware repo cache helpers.
- Modify `delivery_runtime/api/schemas.py`: add provider-neutral repository and project config fields.
- Modify `delivery_runtime/api/routes.py`: add provider-aware repository listing endpoint while preserving `/gitlab-repos`.
- Modify `delivery_runtime/context/repo_checkout.py`: route managed clone URL building through the active VCS provider.
- Modify `lc_server/provisioning/prerequisites.py`: require GitHub MCP or GitLab MCP depending on `vcs`.
- Modify `lc_server/agent_bridge/delivery_toolsets.py`: resolve publisher MCP toolsets from the project provider.
- Modify `lc_server/agent_bridge/hermes_publisher.py`: accept provider-neutral completion blocks and verify through provider adapters.
- Modify `delivery_runtime/mr_drafts/models.py` and `delivery_runtime/mr_drafts/store.py`: add provider-neutral review request fields while preserving MR reads.
- Modify `delivery_runtime/shadow/guards.py`: block GitHub write tools with the same publisher role exception as GitLab.
- Create `ui/src/lib/github-mcp.ts`: GitHub MCP config helpers.
- Create `ui/src/lib/integrations/github-token-dialog.tsx`: GitHub token dialog.
- Modify `ui/src/hermes.ts`: add GitHub MCP status/connect helpers.
- Modify `ui/src/lib/delivery.ts`: add VCS provider types and provider-aware repo listing.
- Modify `ui/src/app/delivery/project-integrations.tsx`: add provider selector, GitHub card, GitHub repo picker, provider-aware labels.
- Modify `ui/src/app/delivery/mr-draft-review-panel.tsx` and related gate display helpers: show PR for GitHub and MR for GitLab.
- Modify README after behavior is implemented.

## Task 1: Provider Resolution and Project Settings

**Files:**
- Create: `lc_server/integrations/vcs/__init__.py`
- Create: `lc_server/integrations/vcs/provider.py`
- Modify: `delivery_runtime/readiness/project_settings.py`
- Modify: `delivery_runtime/api/schemas.py`
- Modify: `delivery_runtime/api/routes.py`
- Test: `tests/delivery_runtime/test_project_settings.py`
- Test: `tests/lc_server/test_vcs_provider.py`

- [ ] **Step 1: Write provider resolution tests**

Add `tests/lc_server/test_vcs_provider.py`:

```python
from __future__ import annotations

import pytest


def test_normalize_vcs_provider_defaults_to_gitlab():
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    assert normalize_vcs_provider(None) == "gitlab"
    assert normalize_vcs_provider("") == "gitlab"


def test_normalize_vcs_provider_accepts_github():
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    assert normalize_vcs_provider(" github ") == "github"


def test_normalize_vcs_provider_rejects_unknown():
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    with pytest.raises(ValueError, match="Unsupported VCS provider"):
        normalize_vcs_provider("bitbucket")
```

- [ ] **Step 2: Write project settings tests**

Add to `tests/delivery_runtime/test_project_settings.py`:

```python
def test_project_vcs_provider_defaults_to_gitlab(tmp_path, monkeypatch):
    from delivery_runtime.readiness.project_settings import load_project_vcs_provider

    assert load_project_vcs_provider("BN") == "gitlab"


def test_persist_project_vcs_provider_writes_mapping(livingcolor_home):
    from delivery_runtime.readiness.project_mapping import load_project_mapping
    from delivery_runtime.readiness.project_settings import (
        load_project_vcs_provider,
        persist_project_vcs_provider,
    )

    assert persist_project_vcs_provider("BN", "github") == "github"
    assert load_project_vcs_provider("BN") == "github"
    assert load_project_mapping()["BN"]["vcs"] == "github"
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
pytest tests/lc_server/test_vcs_provider.py tests/delivery_runtime/test_project_settings.py -k "vcs_provider or normalize_vcs_provider" -v
```

Expected: FAIL because `lc_server.integrations.vcs.provider` and project setting helpers do not exist.

- [ ] **Step 4: Create VCS provider constants and normalization**

Create `lc_server/integrations/vcs/__init__.py`:

```python
"""Version-control provider integration boundary for LivingColor."""
```

Create `lc_server/integrations/vcs/provider.py`:

```python
"""Shared VCS provider types and resolution helpers."""

from __future__ import annotations

from typing import Literal

VcsProviderName = Literal["gitlab", "github"]
DEFAULT_VCS_PROVIDER: VcsProviderName = "gitlab"
SUPPORTED_VCS_PROVIDERS: tuple[VcsProviderName, ...] = ("gitlab", "github")


def normalize_vcs_provider(value: object) -> VcsProviderName:
    raw = str(value or "").strip().lower()
    if not raw:
        return DEFAULT_VCS_PROVIDER
    if raw in SUPPORTED_VCS_PROVIDERS:
        return raw  # type: ignore[return-value]
    raise ValueError(f"Unsupported VCS provider: {raw}")
```

- [ ] **Step 5: Add project setting helpers**

Modify `delivery_runtime/readiness/project_settings.py`:

```python
def load_project_vcs_provider(project_key: str) -> str:
    """Return the configured VCS provider for a project; defaults to GitLab."""
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    entry = _mapping_entry(_normalize_project_key(project_key))
    return normalize_vcs_provider(entry.get("vcs"))


def persist_project_vcs_provider(project_key: str, vcs_provider: str) -> str:
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    key = _normalize_project_key(project_key)
    provider = normalize_vcs_provider(vcs_provider)

    def _update(entry: dict[str, Any]) -> None:
        entry["vcs"] = provider

    _upsert_mapping_entry(key, _update)
    return provider
```

- [ ] **Step 6: Expose provider in project config schemas and routes**

Modify `delivery_runtime/api/schemas.py` project config response/request classes to include:

```python
vcs: str = "gitlab"
```

Modify `_project_config_response()` in `delivery_runtime/api/routes.py` to set `vcs=load_project_vcs_provider(project_key)`.

Modify project config update handling to call `persist_project_vcs_provider(project_key, request.vcs)` when the request carries a provider value.

- [ ] **Step 7: Run tests and commit**

Run:

```bash
pytest tests/lc_server/test_vcs_provider.py tests/delivery_runtime/test_project_settings.py -k "vcs_provider or normalize_vcs_provider" -v
```

Expected: PASS.

Commit:

```bash
git add lc_server/integrations/vcs delivery_runtime/readiness/project_settings.py delivery_runtime/api/schemas.py delivery_runtime/api/routes.py tests/lc_server/test_vcs_provider.py tests/delivery_runtime/test_project_settings.py
git commit -m "feat: add project VCS provider setting"
```

## Task 2: GitHub MCP Helpers and Dynamic Prerequisites

**Files:**
- Create: `lc_server/integrations/vcs/github.py`
- Modify: `lc_server/provisioning/prerequisites.py`
- Test: `tests/lc_server/test_provisioning.py`
- Create: `ui/src/lib/github-mcp.ts`
- Test: `ui/src/lib/github-mcp.test.ts`

- [ ] **Step 1: Write backend prerequisite tests**

Add to `tests/lc_server/test_provisioning.py`:

```python
def test_prerequisites_require_github_when_project_uses_github(monkeypatch):
    from lc_server.provisioning.prerequisites import check_provisioning_prerequisites

    servers = {
        "jira": {"env": {"JIRA_URL": "https://jira.example.com", "JIRA_API_TOKEN": "token"}},
        "github": {"env": {"GITHUB_TOKEN": "ghp_test"}},
    }

    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.load_project_vcs_provider",
        lambda project_key: "github",
    )
    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.resolve_project_mcp_server",
        lambda _project_key, server_name: servers.get(server_name),
    )
    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.is_delivery_llm_available",
        lambda: True,
    )

    assert check_provisioning_prerequisites("GH") == []


def test_prerequisites_do_not_require_gitlab_for_github(monkeypatch):
    from lc_server.provisioning.prerequisites import check_provisioning_prerequisites

    servers = {
        "jira": {"env": {"JIRA_URL": "https://jira.example.com", "JIRA_API_TOKEN": "token"}},
    }

    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.load_project_vcs_provider",
        lambda project_key: "github",
    )
    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.resolve_project_mcp_server",
        lambda _project_key, server_name: servers.get(server_name),
    )
    monkeypatch.setattr(
        "lc_server.provisioning.prerequisites.is_delivery_llm_available",
        lambda: True,
    )

    assert check_provisioning_prerequisites("GH") == ["github_mcp"]
```

- [ ] **Step 2: Write frontend GitHub MCP tests**

Create `ui/src/lib/github-mcp.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'

import {
  GITHUB_MCP_PACKAGE,
  GITHUB_MCP_PRESET_NAME,
  buildGitHubMcpConfig,
  readGitHubSavedCredentials
} from './github-mcp'

describe('github-mcp', () => {
  it('builds GitHub MCP server config', () => {
    expect(buildGitHubMcpConfig({ apiToken: ' ghp_test ' })).toEqual({
      command: 'npx',
      args: ['-y', GITHUB_MCP_PACKAGE],
      connect_timeout: 120,
      env: { GITHUB_TOKEN: 'ghp_test' }
    })
    expect(GITHUB_MCP_PRESET_NAME).toBe('github')
  })

  it('reads saved GitHub credentials', () => {
    expect(readGitHubSavedCredentials({ env: { GITHUB_TOKEN: 'ghp_saved' } })).toEqual({
      apiToken: 'ghp_saved',
      usesEnvAuth: true
    })
  })
})
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
pytest tests/lc_server/test_provisioning.py -k "github and prerequisites" -v
cd ui && npx vitest run src/lib/github-mcp.test.ts
```

Expected: FAIL because GitHub prerequisite and frontend helper are missing.

- [ ] **Step 4: Implement GitHub MCP frontend helper**

Create `ui/src/lib/github-mcp.ts`:

```typescript
export const GITHUB_MCP_PRESET_NAME = 'github'
export const GITHUB_PERSONAL_ACCESS_TOKEN_URL = 'https://github.com/settings/tokens'
export const GITHUB_MCP_PACKAGE = '@modelcontextprotocol/server-github'

export interface GitHubEnvCredentials {
  apiToken: string
}

export interface GitHubSavedCredentials {
  apiToken: string | null
  usesEnvAuth: boolean
}

function readEnvRecord(serverConfig: Record<string, unknown> | undefined): Record<string, string> {
  const env = serverConfig?.env
  if (!env || typeof env !== 'object' || Array.isArray(env)) {
    return {}
  }
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(env as Record<string, unknown>)) {
    if (typeof value === 'string' && value.trim()) {
      out[key] = value.trim()
    }
  }
  return out
}

export function buildGitHubMcpConfig(credentials: GitHubEnvCredentials): Record<string, unknown> {
  return {
    command: 'npx',
    args: ['-y', GITHUB_MCP_PACKAGE],
    connect_timeout: 120,
    env: {
      GITHUB_TOKEN: credentials.apiToken.trim()
    }
  }
}

export function readGitHubSavedCredentials(
  serverConfig: Record<string, unknown> | undefined
): GitHubSavedCredentials {
  const token = readEnvRecord(serverConfig).GITHUB_TOKEN ?? null
  return token ? { apiToken: token, usesEnvAuth: true } : { apiToken: null, usesEnvAuth: false }
}
```

- [ ] **Step 5: Implement provider-aware prerequisites**

Modify `lc_server/provisioning/prerequisites.py`:

```python
from delivery_runtime.readiness.project_settings import load_project_vcs_provider, resolve_project_mcp_server

_GITHUB_MCP_CODE = "github_mcp"


def _provider_mcp_code(provider: str) -> tuple[str, str]:
    if provider == "github":
        return "github", _GITHUB_MCP_CODE
    return "gitlab", _GITLAB_MCP_CODE
```

Then update `check_provisioning_prerequisites()`:

```python
provider = load_project_vcs_provider(project_key)
server_name, missing_code = _provider_mcp_code(provider)
if not _is_mcp_server_configured(resolve_project_mcp_server(project_key, server_name)):
    missing.append(missing_code)
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
pytest tests/lc_server/test_provisioning.py -k "prerequisites" -v
cd ui && npx vitest run src/lib/github-mcp.test.ts
```

Expected: PASS.

Commit:

```bash
git add lc_server/provisioning/prerequisites.py ui/src/lib/github-mcp.ts ui/src/lib/github-mcp.test.ts tests/lc_server/test_provisioning.py
git commit -m "feat: add GitHub MCP prerequisites"
```

## Task 3: Provider-Aware Repository Discovery API

**Files:**
- Create: `lc_server/integrations/vcs/github.py`
- Modify: `delivery_runtime/api/schemas.py`
- Modify: `delivery_runtime/api/routes.py`
- Modify: `delivery_runtime/readiness/project_settings.py`
- Test: `tests/lc_server/test_github_discovery.py`
- Test: `tests/delivery_runtime/test_delivery_api.py`

- [ ] **Step 1: Write GitHub discovery tests**

Create `tests/lc_server/test_github_discovery.py`:

```python
from __future__ import annotations

from unittest.mock import patch


def test_discover_github_repos_prefers_project_key_match():
    from lc_server.integrations.vcs.github import discover_github_repos

    repos = [
        {"full_name": "org/gh-service", "name": "gh-service", "updated_at": "2026-06-10T00:00:00Z"},
        {"full_name": "org/other", "name": "other", "updated_at": "2026-06-11T00:00:00Z"},
    ]

    result = discover_github_repos("GH", repos)

    assert result.default_repo == "github.com/org/gh-service"
    assert result.repos == [{"path": "github.com/org/gh-service", "githubId": None}]
    assert result.warnings == []


def test_discover_github_repos_for_project_uses_fetch():
    from lc_server.integrations.vcs.github import discover_github_repos_for_project

    mcp_config = {"env": {"GITHUB_TOKEN": "ghp_test"}}
    fetched = [{"id": 1, "full_name": "org/app", "name": "app", "updated_at": "2026-06-11T00:00:00Z"}]

    with patch("lc_server.integrations.vcs.github._fetch_github_repositories", return_value=fetched) as mock_fetch:
        result = discover_github_repos_for_project("APP", mcp_config)

    mock_fetch.assert_called_once_with(mcp_config)
    assert result.default_repo == "github.com/org/app"
    assert result.repos[0]["githubId"] == 1
```

- [ ] **Step 2: Run failing discovery tests**

Run:

```bash
pytest tests/lc_server/test_github_discovery.py -v
```

Expected: FAIL because `lc_server.integrations.vcs.github` does not exist.

- [ ] **Step 3: Implement GitHub repository discovery**

Create `lc_server/integrations/vcs/github.py` with:

```python
"""GitHub.com VCS provider helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

_GITHUB_API_URL = "https://api.github.com"
_FETCH_TIMEOUT_SECONDS = 30


@dataclass
class GitHubDiscoveryResult:
    repos: list[dict[str, Any]] = field(default_factory=list)
    default_repo: str | None = None
    warnings: list[str] = field(default_factory=list)


def _read_mcp_env(mcp_config: dict) -> dict[str, str]:
    env = mcp_config.get("env") or {}
    if not isinstance(env, dict):
        return {}
    return {str(k): str(v).strip() for k, v in env.items() if v is not None and str(v).strip()}


def _project_matches_key(repo: dict[str, Any], project_key: str) -> bool:
    key = project_key.casefold()
    full_name = str(repo.get("full_name") or "").casefold()
    name = str(repo.get("name") or "").casefold()
    return key in full_name or key in name


def _to_repo_entry(repo: dict[str, Any]) -> dict[str, Any]:
    full_name = str(repo.get("full_name") or "").strip("/")
    return {"path": f"github.com/{full_name}" if full_name else "", "githubId": repo.get("id")}


def discover_github_repos(project_key: str, repos: list[dict]) -> GitHubDiscoveryResult:
    normalized_key = (project_key or "").strip()
    if not repos:
        return GitHubDiscoveryResult()
    if len(repos) == 1:
        entry = _to_repo_entry(repos[0])
        return GitHubDiscoveryResult(repos=[entry], default_repo=entry["path"] or None)
    matches = [repo for repo in repos if _project_matches_key(repo, normalized_key)]
    if matches:
        best = max(matches, key=lambda repo: str(repo.get("updated_at") or ""))
        return GitHubDiscoveryResult(
            repos=[_to_repo_entry(repo) for repo in matches],
            default_repo=_to_repo_entry(best)["path"] or None,
        )
    sorted_repos = sorted(repos, key=lambda repo: str(repo.get("full_name") or "").casefold())
    default = _to_repo_entry(sorted_repos[0])["path"] or None
    return GitHubDiscoveryResult(
        repos=[_to_repo_entry(repo) for repo in sorted_repos],
        default_repo=default,
        warnings=[f"No GitHub repository matched project key {normalized_key!r}; defaulting to the first repository alphabetically."],
    )


def _fetch_github_repositories(mcp_config: dict) -> list[dict]:
    token = _read_mcp_env(mcp_config).get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GitHub token is required in MCP config env (GITHUB_TOKEN)")
    repos: list[dict] = []
    page = 1
    while page <= 50:
        url = f"{_GITHUB_API_URL}/user/repos?affiliation=owner,collaborator,organization_member&per_page=100&page={page}"
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API request failed ({exc.code}): {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc
        if not isinstance(payload, list):
            raise RuntimeError("GitHub API returned an unexpected repositories payload")
        if not payload:
            break
        repos.extend(dict(item) for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            break
        page += 1
    return repos


def discover_github_repos_for_project(project_key: str, mcp_config: dict) -> GitHubDiscoveryResult:
    return discover_github_repos(project_key, _fetch_github_repositories(mcp_config))
```

- [ ] **Step 4: Add provider-neutral repo schemas**

Modify `delivery_runtime/api/schemas.py` near `GitLabRepoPayload`:

```python
class VcsRepoPayload(BaseModel):
    path: str
    gitlabId: int | None = None
    githubId: int | None = None


class VcsReposResponse(BaseModel):
    items: list[VcsRepoPayload]
    defaultRepo: str | None = None
    provider: str = "gitlab"
```

- [ ] **Step 5: Add provider-aware route**

Add to `delivery_runtime/api/routes.py`:

```python
@router.get("/projects/{project_key}/vcs-repos", response_model=VcsReposResponse)
def list_project_vcs_repos(project_key: str) -> VcsReposResponse:
    from delivery_runtime.readiness.project_settings import (
        load_project_default_repo,
        load_project_gitlab_repos,
        load_project_vcs_provider,
        resolve_project_mcp_server,
    )
    from lc_server.integrations.vcs.github import discover_github_repos_for_project
    from lc_server.provisioning.gitlab_discovery import discover_gitlab_repos_for_project

    key = project_key.strip().upper()
    provider = load_project_vcs_provider(key)
    mcp_config = resolve_project_mcp_server(key, provider)
    if not mcp_config:
        raise HTTPException(status_code=400, detail={"error": f"{provider}_mcp_not_configured"})

    try:
        if provider == "github":
            discovery = discover_github_repos_for_project(key, mcp_config)
            repos = discovery.repos
        else:
            discovery = discover_gitlab_repos_for_project(key, mcp_config)
            repos = discovery.repos or load_project_gitlab_repos(key)
    except Exception as exc:
        if provider == "gitlab":
            cached = load_project_gitlab_repos(key)
            if cached:
                return VcsReposResponse(items=[VcsRepoPayload.model_validate(item) for item in cached], defaultRepo=load_project_default_repo(key), provider=provider)
        raise HTTPException(status_code=502, detail=f"{provider.title()} repository listing failed: {exc}") from exc

    return VcsReposResponse(
        items=[VcsRepoPayload.model_validate(item) for item in repos],
        defaultRepo=load_project_default_repo(key) or discovery.default_repo,
        provider=provider,
    )
```

Keep `/gitlab-repos` unchanged for compatibility.

- [ ] **Step 6: Run tests and commit**

Run:

```bash
pytest tests/lc_server/test_github_discovery.py tests/delivery_runtime/test_delivery_api.py -k "github or vcs_repos or gitlab_repos" -v
```

Expected: PASS after route tests are added or adjusted.

Commit:

```bash
git add lc_server/integrations/vcs/github.py delivery_runtime/api/schemas.py delivery_runtime/api/routes.py tests/lc_server/test_github_discovery.py tests/delivery_runtime/test_delivery_api.py
git commit -m "feat: add GitHub repository discovery"
```

## Task 4: Managed Checkout for GitHub

**Files:**
- Modify: `delivery_runtime/context/repo_checkout.py`
- Modify: `lc_server/integrations/vcs/github.py`
- Create or modify: `lc_server/integrations/vcs/gitlab.py`
- Test: `tests/delivery_runtime/test_repo_checkout.py`

- [ ] **Step 1: Write GitHub checkout tests**

Add to `tests/delivery_runtime/test_repo_checkout.py`:

```python
def test_ensure_managed_checkout_clones_github_when_project_uses_github(_isolate_hermes_home):
    target = managed_checkout_path("GH", "github.com/org/demo-repo")

    def fake_clone(url: str, destination: Path) -> bool:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / ".git").mkdir()
        return True

    project_cfg = {
        "vcs": "github",
        "integrations": {
            "mcp_servers": {
                "github": {"env": {"GITHUB_TOKEN": "ghp_test"}}
            }
        },
    }

    with patch("delivery_runtime.context.repo_checkout.managed_checkout_path", return_value=target), patch(
        "delivery_runtime.context.repo_checkout._clone_repository", side_effect=fake_clone
    ) as clone_mock:
        result = ensure_managed_checkout(project_key="GH", repo_id="github.com/org/demo-repo", project_cfg=project_cfg)

    assert result == str(target)
    clone_mock.assert_called_once()
    assert "x-access-token:ghp_test@github.com/org/demo-repo.git" in clone_mock.call_args.args[0]


def test_ensure_managed_checkout_without_github_token_returns_none(_isolate_hermes_home):
    result = ensure_managed_checkout(
        project_key="GH",
        repo_id="github.com/org/demo-repo",
        project_cfg={"vcs": "github", "integrations": {}},
    )
    assert result is None
```

- [ ] **Step 2: Run failing checkout tests**

Run:

```bash
pytest tests/delivery_runtime/test_repo_checkout.py -k "github or managed_checkout" -v
```

Expected: FAIL because checkout only reads GitLab credentials.

- [ ] **Step 3: Add clone URL helpers**

Add to `lc_server/integrations/vcs/github.py`:

```python
from urllib.parse import quote


def github_token_from_config(mcp_config: dict) -> str | None:
    return _read_mcp_env(mcp_config).get("GITHUB_TOKEN")


def build_github_clone_url(repo_id: str, token: str) -> str:
    repo_path = repo_id.strip().removeprefix("github.com/").strip("/")
    return f"https://x-access-token:{quote(token, safe='')}@github.com/{repo_path}.git"
```

Create `lc_server/integrations/vcs/gitlab.py`:

```python
"""GitLab VCS provider compatibility helpers."""

from __future__ import annotations

from urllib.parse import quote, urlparse


def gitlab_token_from_config(mcp_config: dict) -> str | None:
    env = mcp_config.get("env") or {}
    if not isinstance(env, dict):
        return None
    token = env.get("GITLAB_PERSONAL_ACCESS_TOKEN") or env.get("GITLAB_TOKEN")
    return str(token).strip() if token else None


def build_gitlab_clone_url(repo_id: str, mcp_config: dict) -> str | None:
    token = gitlab_token_from_config(mcp_config)
    if not token:
        return None
    env = mcp_config.get("env") if isinstance(mcp_config.get("env"), dict) else {}
    api_url = str(env.get("GITLAB_API_URL") or "https://gitlab.com/api/v4")
    parsed = urlparse(api_url.strip())
    host = parsed.netloc or "gitlab.com"
    scheme = parsed.scheme or "https"
    return f"{scheme}://oauth2:{quote(token, safe='')}@{host}/{repo_id.strip('/')}.git"
```

- [ ] **Step 4: Route checkout through provider**

Modify `_build_clone_url()` in `delivery_runtime/context/repo_checkout.py`:

```python
def _build_clone_url(
    repo_id: str,
    project_cfg: dict[str, Any],
    *,
    project_key: str | None = None,
) -> str | None:
    from delivery_runtime.readiness.project_settings import resolve_project_mcp_server
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    provider = normalize_vcs_provider(project_cfg.get("vcs"))
    key = (project_key or "").strip().upper()
    if provider == "github":
        from lc_server.integrations.vcs.github import build_github_clone_url, github_token_from_config

        config = _project_or_global_mcp_config(project_cfg, "github", key)
        token = github_token_from_config(config)
        return build_github_clone_url(repo_id, token) if token else None

    from lc_server.integrations.vcs.gitlab import build_gitlab_clone_url

    config = _project_or_global_mcp_config(project_cfg, "gitlab", key)
    return build_gitlab_clone_url(repo_id, config)
```

Add helper in the same file:

```python
def _project_or_global_mcp_config(project_cfg: dict[str, Any], server_name: str, project_key: str) -> dict[str, Any]:
    integrations = project_cfg.get("integrations") if isinstance(project_cfg, dict) else {}
    integrations_map = integrations if isinstance(integrations, dict) else {}
    servers = integrations_map.get("mcp_servers")
    servers_map = servers if isinstance(servers, dict) else {}
    direct = servers_map.get(server_name)
    if isinstance(direct, dict) and direct:
        return dict(direct)
    if project_key:
        from delivery_runtime.readiness.project_settings import resolve_project_mcp_server

        return resolve_project_mcp_server(project_key, server_name)
    return {}
```

Keep `has_gitlab_clone_credentials()` for compatibility and add `has_clone_credentials()` for provider-aware callers.

- [ ] **Step 5: Update developer error text**

Modify `lc_server/agent_bridge/hermes_developer.py` to call `has_clone_credentials()` and use provider-aware error text:

```python
if not has_clone_credentials(project_cfg, project_key=project_key):
    provider = str(project_cfg.get("vcs") or "gitlab")
    raise ValueError(
        "Developer Agent requires a local repository checkout at "
        f"{expected_path}. {provider.title()} credentials are missing for project {project_key} "
        f"(configure integrations.mcp_servers.{provider} in project_mapping.yaml or global Hermes MCP)."
    )
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
pytest tests/delivery_runtime/test_repo_checkout.py tests/lc_server/test_hermes_developer.py -v
```

Expected: PASS.

Commit:

```bash
git add delivery_runtime/context/repo_checkout.py lc_server/integrations/vcs/github.py lc_server/integrations/vcs/gitlab.py lc_server/agent_bridge/hermes_developer.py tests/delivery_runtime/test_repo_checkout.py
git commit -m "feat: support GitHub managed checkouts"
```

## Task 5: Provider-Neutral Publisher Completion and Verification

**Files:**
- Modify: `lc_server/agent_bridge/hermes_publisher.py`
- Modify: `lc_server/integrations/gitlab_mr_verification.py`
- Modify: `lc_server/integrations/vcs/github.py`
- Test: `tests/lc_server/test_publisher_completion_parsing.py`
- Test: `tests/lc_server/test_github_pr_verification.py`

- [ ] **Step 1: Write completion parsing tests**

Add to `tests/lc_server/test_publisher_completion_parsing.py`:

```python
def test_parses_provider_neutral_github_completion():
    from lc_server.agent_bridge.hermes_publisher import parse_publisher_completion

    text = (
        "Pushed and created the PR.\n"
        '```json\n{"reviewRequestUrl": "https://github.com/org/app/pull/42", '
        '"reviewRequestNumber": 42, "targetBranch": "main", '
        '"provider": "github", "status": "published"}\n```'
    )

    result = parse_publisher_completion(text)

    assert result["reviewRequestUrl"] == "https://github.com/org/app/pull/42"
    assert result["reviewRequestNumber"] == 42
    assert result["reviewRequestProvider"] == "github"
    assert result["mrUrl"] == "https://github.com/org/app/pull/42"
    assert result["mrIid"] == 42
```

- [ ] **Step 2: Write GitHub PR verification tests**

Create `tests/lc_server/test_github_pr_verification.py`:

```python
from __future__ import annotations

import pytest


def test_repo_path_and_number_from_github_pr_url():
    from lc_server.integrations.vcs.github import repo_path_and_number_from_pr_url

    assert repo_path_and_number_from_pr_url("https://github.com/org/app/pull/42") == ("org/app", 42)


def test_repo_path_and_number_rejects_non_pr_url():
    from lc_server.integrations.vcs.github import repo_path_and_number_from_pr_url

    with pytest.raises(ValueError, match="not a GitHub PR url"):
        repo_path_and_number_from_pr_url("https://github.com/org/app/issues/42")
```

- [ ] **Step 3: Run failing publisher tests**

Run:

```bash
pytest tests/lc_server/test_publisher_completion_parsing.py tests/lc_server/test_github_pr_verification.py -k "github or neutral or repo_path" -v
```

Expected: FAIL because parser and GitHub PR URL helper are missing.

- [ ] **Step 4: Add GitHub PR URL and verification helpers**

Add to `lc_server/integrations/vcs/github.py`:

```python
import urllib.error
import urllib.parse


def repo_path_and_number_from_pr_url(pr_url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(pr_url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if parsed.netloc.lower() != "github.com" or len(parts) != 4 or parts[2] != "pull":
        raise ValueError(f"not a GitHub PR url: {pr_url}")
    return f"{parts[0]}/{parts[1]}", int(parts[3])


def verify_pull_request_exists(*, mcp_config: dict, repo_path: str, pr_number: int) -> dict[str, Any] | None:
    token = github_token_from_config(mcp_config)
    if not token:
        raise ValueError("GitHub token is required in MCP config env (GITHUB_TOKEN)")
    url = f"{_GITHUB_API_URL}/repos/{repo_path.strip('/')}/pulls/{int(pr_number)}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub PR verification failed ({exc.code}): {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub PR verification failed: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub API returned an unexpected pull request payload")
    return payload
```

- [ ] **Step 5: Generalize completion parsing**

Modify `parse_publisher_completion()` in `lc_server/agent_bridge/hermes_publisher.py`:

```python
review_url = str(payload.get("reviewRequestUrl") or payload.get("mrUrl") or "")
review_number = payload.get("reviewRequestNumber", payload.get("mrIid"))
provider = str(payload.get("provider") or payload.get("reviewRequestProvider") or "gitlab")
if not isinstance(review_number, int) or isinstance(review_number, bool) or not review_url:
    raise PublisherCompletionError("publisher completion missing review request url/number")
return {
    "reviewRequestUrl": review_url,
    "reviewRequestNumber": review_number,
    "reviewRequestProvider": provider,
    "mrUrl": review_url,
    "mrIid": review_number,
    "targetBranch": str(payload.get("targetBranch") or ""),
    "status": "published",
}
```

- [ ] **Step 6: Verify through active provider**

Modify `_verify_mr_exists()` into `_verify_review_request_exists()`:

```python
provider = str(completion.get("reviewRequestProvider") or "gitlab")
if provider == "github":
    from delivery_runtime.readiness.project_settings import resolve_project_mcp_server
    from lc_server.integrations.vcs.github import (
        repo_path_and_number_from_pr_url,
        verify_pull_request_exists,
    )

    mcp_config = resolve_project_mcp_server(project_key or "", "github")
    repo_path, pr_number = repo_path_and_number_from_pr_url(completion["reviewRequestUrl"])
    found = verify_pull_request_exists(mcp_config=mcp_config, repo_path=repo_path, pr_number=pr_number)
    if found is None:
        raise PublisherCompletionError("PR not found in GitHub after publication")
    return
```

Keep GitLab verification as the `else` branch.

- [ ] **Step 7: Run tests and commit**

Run:

```bash
pytest tests/lc_server/test_publisher_completion_parsing.py tests/lc_server/test_github_pr_verification.py -v
```

Expected: PASS.

Commit:

```bash
git add lc_server/agent_bridge/hermes_publisher.py lc_server/integrations/vcs/github.py tests/lc_server/test_publisher_completion_parsing.py tests/lc_server/test_github_pr_verification.py
git commit -m "feat: support provider-neutral publication results"
```

## Task 6: Provider-Aware Publisher Prompts and Toolsets

**Files:**
- Modify: `lc_server/agent_bridge/hermes_publisher.py`
- Modify: `lc_server/agent_bridge/delivery_toolsets.py`
- Modify: `lc_server/agent_templates/v1/publisher.yaml.tmpl`
- Test: `tests/lc_server/test_publisher_completion_parsing.py`
- Test: `tests/lc_server/test_delivery_toolsets.py`
- Test: `tests/lc_server/test_publisher_template.py`

- [ ] **Step 1: Write publisher prompt tests**

Add to `tests/lc_server/test_publisher_completion_parsing.py`:

```python
def test_build_publisher_prompt_uses_github_terms():
    from lc_server.agent_bridge.hermes_publisher import build_publisher_prompt

    prompt = build_publisher_prompt(
        {
            "workspacePath": "/repo",
            "deliveryBranch": "feature/GH-1",
            "integrationBranch": "main",
            "mrTitle": "GH-1: change",
            "mrDescription": "Approved body",
            "vcs": "github",
        }
    )

    assert "Publish the approved delivery branch to GitHub" in prompt
    assert "Pull Request title" in prompt
    assert "GitHub MCP create_pull_request" in prompt
    assert "Merge request" not in prompt
```

- [ ] **Step 2: Write toolset tests**

Create `tests/lc_server/test_delivery_toolsets.py` or add to an existing toolset test:

```python
def test_resolve_publisher_toolsets_uses_github_server(monkeypatch):
    from lc_server.agent_bridge.delivery_toolsets import resolve_publisher_toolsets

    monkeypatch.setattr(
        "lc_server.agent_bridge.delivery_toolsets._project_mcp_server_names",
        lambda project_key: ["github"],
    )
    monkeypatch.setattr(
        "lc_server.agent_bridge.delivery_toolsets._configured_mcp_server_names",
        lambda: [],
    )
    monkeypatch.setattr(
        "lc_server.agent_bridge.delivery_toolsets.load_project_vcs_provider",
        lambda project_key: "github",
    )

    assert "mcp-github" in resolve_publisher_toolsets(
        base_toolsets=["terminal", "skills"],
        manifest=None,
        project_key="GH",
    )
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
pytest tests/lc_server/test_publisher_completion_parsing.py -k github_terms -v
pytest tests/lc_server/test_delivery_toolsets.py -v
```

Expected: FAIL until prompt/toolset code is provider-aware.

- [ ] **Step 4: Generalize publisher prompt builder**

Modify `build_publisher_prompt()`:

```python
vcs = str(context.get("vcs") or context.get("reviewRequestProvider") or "gitlab").strip().lower()
is_github = vcs == "github"
provider_label = "GitHub" if is_github else "GitLab"
request_label = "Pull Request" if is_github else "Merge request"
mcp_create_tool = "create_pull_request" if is_github else "create_merge_request"
```

Use these variables for all provider-specific prompt text. The GitHub instruction line should say:

```python
f"ONLY with the {provider_label} MCP {mcp_create_tool} tool (no curl, no REST fallbacks)."
```

- [ ] **Step 5: Resolve publisher MCP toolsets from provider**

Modify `lc_server/agent_bridge/delivery_toolsets.py`:

```python
from delivery_runtime.readiness.project_settings import load_project_vcs_provider


def _vcs_mcp_server_names(project_key: str | None) -> list[str]:
    provider = load_project_vcs_provider(project_key or "") if project_key else "gitlab"
    names: list[str] = []
    for server_name in dict.fromkeys(_project_mcp_server_names(project_key) + _configured_mcp_server_names()):
        if provider in server_name.lower():
            names.append(server_name)
    return names or [provider]
```

Update `resolve_publisher_toolsets()` to append `_vcs_mcp_server_names(project_key)`.

- [ ] **Step 6: Update publisher manifest template**

Modify `lc_server/agent_templates/v1/publisher.yaml.tmpl` to use provider-neutral language:

```yaml
    Your ONLY job is to publish an already-approved delivery branch to the configured VCS provider:
    push the branch, ensure the integration branch exists, and create the review request.
```

Keep GitLab-compatible rules but replace hardcoded "Merge Request" with "review request" where the manifest is provider-neutral.

- [ ] **Step 7: Run tests and commit**

Run:

```bash
pytest tests/lc_server/test_publisher_completion_parsing.py tests/lc_server/test_delivery_toolsets.py tests/lc_server/test_publisher_template.py -v
```

Expected: PASS.

Commit:

```bash
git add lc_server/agent_bridge/hermes_publisher.py lc_server/agent_bridge/delivery_toolsets.py lc_server/agent_templates/v1/publisher.yaml.tmpl tests/lc_server/test_publisher_completion_parsing.py tests/lc_server/test_delivery_toolsets.py tests/lc_server/test_publisher_template.py
git commit -m "feat: make publisher provider-aware"
```

## Task 7: Review Request Storage Compatibility

**Files:**
- Modify: `delivery_runtime/mr_drafts/models.py`
- Modify: `delivery_runtime/mr_drafts/store.py`
- Modify: `delivery_runtime/api/schemas.py`
- Modify: `lc_server/agent_bridge/hermes_publisher.py`
- Test: `tests/delivery_runtime/test_mr_draft_store_publication.py`
- Test: `tests/lc_server/test_publisher_completion_parsing.py`

- [ ] **Step 1: Write storage compatibility tests**

Add to `tests/delivery_runtime/test_mr_draft_store_publication.py`:

```python
def test_mr_draft_publication_stores_provider_neutral_fields(livingcolor_home):
    from delivery_runtime.mr_drafts.models import MergeRequestDraft
    from delivery_runtime.mr_drafts.store import load_mr_draft, save_mr_draft, set_mr_draft_publication
    from delivery_runtime.persistence.db import init_db, utc_now_iso

    init_db()
    now = utc_now_iso()
    draft = save_mr_draft(
        MergeRequestDraft(
            id="MRD-GH-1",
            work_order_id="WO-GH-1",
            title="GH-1",
            description="Body",
            ticket_summary="",
            implementation_summary="",
            files_modified=[],
            risks=[],
            reviewers=[],
            qa_checklist={},
            decision_trace={},
            status="approved",
            created_at=now,
            updated_at=now,
        )
    )

    set_mr_draft_publication(
        draft.id,
        review_request_url="https://github.com/org/app/pull/42",
        review_request_number=42,
        review_request_provider="github",
    )

    loaded = load_mr_draft(draft.id)
    assert loaded.review_request_url == "https://github.com/org/app/pull/42"
    assert loaded.review_request_number == 42
    assert loaded.review_request_provider == "github"
    assert loaded.mr_url == "https://github.com/org/app/pull/42"
    assert loaded.mr_iid == 42
```

- [ ] **Step 2: Run failing storage tests**

Run:

```bash
pytest tests/delivery_runtime/test_mr_draft_store_publication.py -k provider_neutral -v
```

Expected: FAIL because neutral fields do not exist.

- [ ] **Step 3: Extend MR draft model**

Modify `delivery_runtime/mr_drafts/models.py` dataclass:

```python
review_request_url: str = ""
review_request_number: int | None = None
review_request_provider: str = "gitlab"
```

Keep `mr_url` and `mr_iid` fields.

- [ ] **Step 4: Extend store mapping without DB migration**

If `merge_request_drafts` has JSON payload/decision fields, store neutral fields in existing columns. If it has explicit columns only, map neutral fields to existing `mr_url` and `mr_iid` columns and set provider in `decision_trace["reviewRequestProvider"]`.

Update `set_mr_draft_publication()` signature:

```python
def set_mr_draft_publication(
    draft_id: str,
    *,
    mr_url: str | None = None,
    mr_iid: int | None = None,
    review_request_url: str | None = None,
    review_request_number: int | None = None,
    review_request_provider: str = "gitlab",
) -> None:
    resolved_url = review_request_url or mr_url or ""
    resolved_number = review_request_number if review_request_number is not None else mr_iid
```

When loading, populate both neutral and legacy fields from the resolved values.

- [ ] **Step 5: Update API response schema**

Modify `MrDraftResponse` in `delivery_runtime/api/schemas.py`:

```python
reviewRequestUrl: str = ""
reviewRequestNumber: int | None = None
reviewRequestProvider: str = "gitlab"
```

Keep `mrUrl` and `mrIid`.

- [ ] **Step 6: Update publisher draft write**

Modify `HermesPublisherAgent.execute()`:

```python
set_mr_draft_publication(
    draft_id,
    review_request_url=completion["reviewRequestUrl"],
    review_request_number=completion["reviewRequestNumber"],
    review_request_provider=completion["reviewRequestProvider"],
)
```

- [ ] **Step 7: Run tests and commit**

Run:

```bash
pytest tests/delivery_runtime/test_mr_draft_store_publication.py tests/lc_server/test_publisher_completion_parsing.py -v
```

Expected: PASS.

Commit:

```bash
git add delivery_runtime/mr_drafts/models.py delivery_runtime/mr_drafts/store.py delivery_runtime/api/schemas.py lc_server/agent_bridge/hermes_publisher.py tests/delivery_runtime/test_mr_draft_store_publication.py tests/lc_server/test_publisher_completion_parsing.py
git commit -m "feat: store provider-neutral review requests"
```

## Task 8: Shadow Guards for GitHub Writes

**Files:**
- Modify: `delivery_runtime/shadow/guards.py`
- Test: `tests/delivery_runtime/test_shadow_guards_publisher.py`

- [ ] **Step 1: Write GitHub shadow guard tests**

Add to `tests/delivery_runtime/test_shadow_guards_publisher.py`:

```python
def test_github_create_pull_request_blocked_without_publisher_role(monkeypatch):
    from delivery_runtime.shadow.guards import check_mcp_tool

    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "1")

    violation = check_mcp_tool("github", "create_pull_request")

    assert violation is not None
    assert violation.category == "github"
    assert violation.operation == "createpullrequest"


def test_github_create_pull_request_allowed_for_publisher(monkeypatch):
    from delivery_runtime.shadow.context import delivery_agent_role
    from delivery_runtime.shadow.guards import check_mcp_tool

    monkeypatch.setenv("LIVINGCOLOR_SHADOW_MODE", "1")

    with delivery_agent_role("publisher"):
        assert check_mcp_tool("github", "create_pull_request") is None
```

- [ ] **Step 2: Run failing shadow tests**

Run:

```bash
pytest tests/delivery_runtime/test_shadow_guards_publisher.py -k github -v
```

Expected: FAIL because GitHub writes are not classified.

- [ ] **Step 3: Add GitHub write tool set**

Modify `delivery_runtime/shadow/guards.py`:

```python
_GITHUB_WRITE_TOOLS = {
    "create_pull_request",
    "createpullrequest",
    "create_branch",
    "createbranch",
    "create_ref",
    "createref",
    "update_pull_request",
    "updatepullrequest",
    "merge_pull_request",
    "mergepullrequest",
    "close_pull_request",
    "closepullrequest",
    "create_issue_comment",
    "createissuecomment",
    "push",
}
```

In `check_mcp_tool()`, add a GitHub branch:

```python
if normalized_server == "github" or "github" in normalized_server:
    if normalized_tool in _GITHUB_WRITE_TOOLS or _looks_like_write_tool(normalized_tool):
        if current_delivery_agent_role() == "publisher":
            return None
        violation = ShadowViolation(
            category="github",
            operation=normalized_tool,
            detail=f"Blocked GitHub write MCP tool {tool_name} in shadow mode",
        )
        _audit_log.record(violation)
        return violation
```

Mirror the same publisher role allowance in standard-mode write checks.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
pytest tests/delivery_runtime/test_shadow_guards_publisher.py -v
```

Expected: PASS.

Commit:

```bash
git add delivery_runtime/shadow/guards.py tests/delivery_runtime/test_shadow_guards_publisher.py
git commit -m "feat: guard GitHub write tools"
```

## Task 9: Dashboard GitHub Integration UI

**Files:**
- Create: `ui/src/lib/integrations/github-token-dialog.tsx`
- Modify: `ui/src/hermes.ts`
- Modify: `ui/src/lib/delivery.ts`
- Modify: `ui/src/app/delivery/project-integrations.tsx`
- Modify: `ui/src/i18n/en.ts`
- Modify: `ui/src/i18n/fr.ts` if present; otherwise update the active locale files that contain integration strings.
- Test: `ui/src/app/delivery/project-integrations.test.tsx`
- Test: `ui/src/lib/cloud-api.test.ts`

- [ ] **Step 1: Add Hermes GitHub API helpers**

Modify `ui/src/hermes.ts`:

```typescript
export function connectGithubMcp(): Promise<GitLabConnectResponse> {
  return callDesktopApi({
    path: `/api/mcp/servers/${encodeURIComponent('github')}/connect`,
    method: 'POST',
    timeoutMs: JIRA_CONNECT_TIMEOUT_MS
  })
}

export function fetchGithubStatus(): Promise<GitLabConnectionStatus> {
  return callDesktopApi({
    path: `/api/mcp/servers/${encodeURIComponent('github')}/status`,
    timeoutMs: JIRA_DASHBOARD_TIMEOUT_MS
  })
}
```

Use a dedicated GitHub status type if the existing GitLab type name causes TypeScript confusion.

- [ ] **Step 2: Add delivery client provider types**

Modify `ui/src/lib/delivery.ts`:

```typescript
export type VcsProvider = 'gitlab' | 'github'

export interface VcsRepoOption {
  path: string
  gitlabId?: number | null
  githubId?: number | null
}

export interface VcsReposPayload {
  items: VcsRepoOption[]
  defaultRepo?: string | null
  provider: VcsProvider
}

export function fetchProjectVcsRepos(projectKey: string): Promise<VcsReposPayload> {
  return callDesktopApi<VcsReposPayload>({
    ...profileScoped(),
    path: `/api/delivery/projects/${encodeURIComponent(projectKey)}/vcs-repos`,
    timeoutMs: 120_000
  })
}
```

Add `vcs?: VcsProvider` to `ProjectConfigPayload` and `saveProjectConfig()` body.

- [ ] **Step 3: Create GitHub token dialog**

Create `ui/src/lib/integrations/github-token-dialog.tsx` using the same structure as `gitlab-token-dialog.tsx`, but with:

```typescript
export interface GitHubCredentialsFormValues {
  apiToken: string
}
```

The dialog should link to `GITHUB_PERSONAL_ACCESS_TOKEN_URL`, label the field `GitHub token`, and submit `{ apiToken }`.

- [ ] **Step 4: Update Project Integrations UI**

Modify `ui/src/app/delivery/project-integrations.tsx`:

- Add `vcsProvider` state from `fetchProjectConfig()`.
- Add selector values `gitlab` and `github`.
- When provider is `github`, call GitHub status helpers, GitHub saved credentials, and `fetchProjectVcsRepos()`.
- When provider is `gitlab`, preserve existing GitLab behavior.
- Save provider changes through `saveProjectConfig({ ..., vcs })`.

Use provider-aware labels:

```typescript
const reviewRequestLabel = vcsProvider === 'github' ? 'PR' : 'MR'
const forgeLabel = vcsProvider === 'github' ? 'GitHub' : 'GitLab'
```

- [ ] **Step 5: Write UI tests**

Add tests in `ui/src/app/delivery/project-integrations.test.tsx`:

```typescript
it('shows GitHub controls when project provider is github', async () => {
  // mock fetchProjectConfig with { vcs: 'github', projectKey: 'GH', ... }
  // render ProjectIntegrationsSection inside the existing test providers
  // assert screen.getByText(/GitHub/i) and screen.getByRole('button', { name: /Connect GitHub/i })
})

it('keeps GitLab controls when project provider is omitted', async () => {
  // mock fetchProjectConfig without vcs
  // assert GitLab controls are visible
})
```

Use the existing test setup patterns in the file if it already exists; create the file with the project workspace provider mocks if it does not.

- [ ] **Step 6: Run UI tests and commit**

Run:

```bash
cd ui && npx vitest run src/lib/github-mcp.test.ts src/app/delivery/project-integrations.test.tsx
```

Expected: PASS.

Commit:

```bash
git add ui/src/hermes.ts ui/src/lib/delivery.ts ui/src/lib/github-mcp.ts ui/src/lib/integrations/github-token-dialog.tsx ui/src/app/delivery/project-integrations.tsx ui/src/i18n ui/src/app/delivery/project-integrations.test.tsx
git commit -m "feat: add GitHub project integration UI"
```

## Task 10: UI Review Request Labels and README

**Files:**
- Modify: `ui/src/app/delivery/mr-draft-review-panel.tsx`
- Modify: `ui/src/app/delivery/gate-payload-formatters.ts`
- Modify: `ui/src/app/delivery/gate-payload-formatters.test.ts`
- Modify: `ui/src/app/delivery/types.ts`
- Modify: `README.md`

- [ ] **Step 1: Write label formatter tests**

Add to `ui/src/app/delivery/gate-payload-formatters.test.ts`:

```typescript
it('formats GitHub review request payloads as PR links', () => {
  const formatted = formatGatePayload({
    reviewRequestProvider: 'github',
    reviewRequestUrl: 'https://github.com/org/app/pull/42',
    reviewRequestNumber: 42
  })

  expect(JSON.stringify(formatted)).toContain('PR')
  expect(JSON.stringify(formatted)).toContain('https://github.com/org/app/pull/42')
})
```

- [ ] **Step 2: Update UI types**

Modify `ui/src/app/delivery/types.ts`:

```typescript
reviewRequestUrl?: string
reviewRequestNumber?: number | null
reviewRequestProvider?: 'gitlab' | 'github' | string
```

Keep `mrUrl` and `mrIid`.

- [ ] **Step 3: Update MR draft panel labels**

Modify `ui/src/app/delivery/mr-draft-review-panel.tsx`:

```typescript
const provider = payload.reviewRequestProvider ?? 'gitlab'
const requestLabel = provider === 'github' ? 'PR' : 'MR'
const requestUrl = payload.reviewRequestUrl || payload.mrUrl
const requestNumber = payload.reviewRequestNumber ?? payload.mrIid
```

Render `Voir la PR #42 sur GitHub` or `Voir la MR !42 sur GitLab` based on provider.

- [ ] **Step 4: Update README**

Modify `README.md` prerequisites and setup sections:

```markdown
3. **GitLab or GitHub MCP** — choose the provider used by each project.
```

Add GitHub mapping example:

```yaml
MYPROJ:
  vcs: github
  default_repo: github.com/org/my-service
  integration_branch: main
```

- [ ] **Step 5: Run UI tests and commit**

Run:

```bash
cd ui && npx vitest run src/app/delivery/gate-payload-formatters.test.ts src/app/delivery/project-integrations.test.tsx
```

Expected: PASS.

Commit:

```bash
git add ui/src/app/delivery/mr-draft-review-panel.tsx ui/src/app/delivery/gate-payload-formatters.ts ui/src/app/delivery/gate-payload-formatters.test.ts ui/src/app/delivery/types.ts README.md
git commit -m "docs: document GitHub provider setup"
```

## Task 11: Final Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run backend test slice**

Run:

```bash
pytest tests/lc_server/test_vcs_provider.py tests/lc_server/test_github_discovery.py tests/lc_server/test_github_pr_verification.py tests/lc_server/test_provisioning.py tests/delivery_runtime/test_repo_checkout.py tests/delivery_runtime/test_shadow_guards_publisher.py tests/lc_server/test_publisher_completion_parsing.py -v
```

Expected: PASS.

- [ ] **Step 2: Run UI test slice**

Run:

```bash
cd ui && npx vitest run src/lib/github-mcp.test.ts src/app/delivery/project-integrations.test.tsx src/app/delivery/gate-payload-formatters.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run broader smoke tests**

Run:

```bash
pytest tests -x -q
cd ui && npm install && npx vite build
```

Expected: backend tests pass; UI bundle builds successfully.

- [ ] **Step 4: Commit build output if changed**

If `dashboard/dist/` changed after `npx vite build`, commit it:

```bash
git add dashboard/dist ui/package-lock.json ui/package.json
git commit -m "build: rebuild plugin UI bundle"
```

If `dashboard/dist/` did not change, skip this commit.

- [ ] **Step 5: Manual smoke script**

Run through this manual checklist:

```text
1. Configure a local project with vcs: github.
2. Save a GitHub token in Project -> Integrations.
3. Pick a GitHub repository from the repo picker.
4. Confirm setup automation no longer asks for GitLab MCP.
5. Run /delivery scan <PROJECT>.
6. Promote one readiness record.
7. Complete gates through publication using a test repository.
8. Confirm a GitHub PR exists and the Work Order displays PR, not MR.
```

Record the manual result in the final implementation summary.
