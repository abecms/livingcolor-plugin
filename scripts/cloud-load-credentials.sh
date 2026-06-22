#!/usr/bin/env bash
# Load LivingColor credentials from ~/.hermes/livingcolor/.env into the shell.
# Safe to source: never prints secret values.
set -euo pipefail

ENV_FILE="${HOME}/.hermes/livingcolor/.env"

if [ ! -f "${ENV_FILE}" ]; then
  return 0 2>/dev/null || exit 0
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# GH_TOKEN alias for GitHub tooling
if [ -z "${GITHUB_TOKEN:-}" ] && [ -n "${GH_TOKEN:-}" ]; then
  export GITHUB_TOKEN="${GH_TOKEN}"
fi
