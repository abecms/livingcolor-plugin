#!/usr/bin/env bash
# Cloud agent environment bootstrap — credentials from Cloud Agent env only.
set -euo pipefail

export PATH="/home/ubuntu/.local/bin:$PATH"
unset LIVINGCOLOR_SHADOW_MODE
export LIVINGCOLOR_SYNC_ORCHESTRATOR=1
export LIVINGCOLOR_DEVELOPER_BACKEND=heuristic
export LIVINGCOLOR_PLANNER_BACKEND=heuristic
export LIVINGCOLOR_ANALYST_BACKEND=heuristic
export LIVINGCOLOR_PUBLISHER_BACKEND=heuristic
export PYTHONPATH="/workspace:${PYTHONPATH:-}"

: "${OPENROUTER_API_KEY:=}"
: "${JIRA_URL:=https://livingcolor.atlassian.net}"
: "${JIRA_USERNAME:=}"
: "${JIRA_API_TOKEN:=}"
: "${GITHUB_TOKEN:=}"
: "${STRIPE_SECRET_KEY:=}"
: "${LIVINGCOLOR_TEST_PROJECT_KEY:=TVP}"
: "${LIVINGCOLOR_TEST_GITHUB_REPO:=abecms/tv5mondeplus-front}"

mkdir -p ~/.hermes/livingcolor

cat > ~/.hermes/config.yaml <<HERMES_EOF
model:
  provider: openrouter
  default: openai/gpt-4o-mini

mcp_servers:
  jira:
    command: /home/ubuntu/.local/bin/mcp-atlassian
    args: []
    env:
      JIRA_URL: https://livingcolor.atlassian.net
      JIRA_USERNAME: PLACEHOLDER_JIRA_USER
      JIRA_API_TOKEN: PLACEHOLDER_JIRA_TOKEN
  github:
    command: npx
    args:
      - -y
      - "@modelcontextprotocol/server-github"
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: PLACEHOLDER_GITHUB_TOKEN
      GITHUB_TOKEN: PLACEHOLDER_GITHUB_TOKEN
HERMES_EOF

sed -i "s|PLACEHOLDER_JIRA_USER|${JIRA_USERNAME}|g" ~/.hermes/config.yaml
sed -i "s|PLACEHOLDER_JIRA_TOKEN|${JIRA_API_TOKEN}|g" ~/.hermes/config.yaml
sed -i "s|PLACEHOLDER_GITHUB_TOKEN|${GITHUB_TOKEN}|g" ~/.hermes/config.yaml

cat > ~/.hermes/livingcolor/project_mapping.yaml <<MAPPING_EOF
TVP:
  jira_project_key: TVP
  vcs: github
  default_repo: github.com/abecms/tv5mondeplus-front
  integration_branch: preprod
  communication_language: fr
  sprint:
    duration_days: 7
    capacity_days: 2.0
  integrations:
    mcp_servers:
      jira:
        command: /home/ubuntu/.local/bin/mcp-atlassian
        args: []
        env:
          JIRA_URL: https://livingcolor.atlassian.net
          JIRA_USERNAME: PLACEHOLDER_JIRA_USER
          JIRA_API_TOKEN: PLACEHOLDER_JIRA_TOKEN
      github:
        command: npx
        args:
          - -y
          - "@modelcontextprotocol/server-github"
        env:
          GITHUB_PERSONAL_ACCESS_TOKEN: PLACEHOLDER_GITHUB_TOKEN
          GITHUB_TOKEN: PLACEHOLDER_GITHUB_TOKEN
MAPPING_EOF

sed -i "s|PLACEHOLDER_JIRA_USER|${JIRA_USERNAME}|g" ~/.hermes/livingcolor/project_mapping.yaml
sed -i "s|PLACEHOLDER_JIRA_TOKEN|${JIRA_API_TOKEN}|g" ~/.hermes/livingcolor/project_mapping.yaml
sed -i "s|PLACEHOLDER_GITHUB_TOKEN|${GITHUB_TOKEN}|g" ~/.hermes/livingcolor/project_mapping.yaml

if [ -n "${STRIPE_SECRET_KEY}" ]; then
  cat > ~/.hermes/livingcolor/.env <<ENV_EOF
STRIPE_SECRET_KEY=PLACEHOLDER_STRIPE
ENV_EOF
  sed -i "s|PLACEHOLDER_STRIPE|${STRIPE_SECRET_KEY}|g" ~/.hermes/livingcolor/.env
fi

if [ -n "${OPENROUTER_API_KEY}" ]; then
  cat > ~/.hermes/.env <<ENV_EOF
OPENROUTER_API_KEY=PLACEHOLDER_OPENROUTER
ENV_EOF
  sed -i "s|PLACEHOLDER_OPENROUTER|${OPENROUTER_API_KEY}|g" ~/.hermes/.env
fi

echo "Environment bootstrap complete"
