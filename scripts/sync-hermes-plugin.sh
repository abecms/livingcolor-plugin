#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${HERMES_LIVINGCOLOR_PLUGIN_DIR:-$HOME/.hermes/plugins/livingcolor}"

echo "Syncing LivingColor plugin to ${TARGET}"

mkdir -p "${TARGET}"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude '.git/' \
    --exclude 'ui/node_modules/' \
    --exclude '**/__pycache__/' \
    --exclude '.cursor/' \
    --exclude 'assets/' \
    "${ROOT}/" "${TARGET}/"
else
  echo "rsync not found; falling back to cp -a"
  rm -rf "${TARGET}"
  mkdir -p "${TARGET}"
  cp -a "${ROOT}/." "${TARGET}/"
  rm -rf "${TARGET}/.git" "${TARGET}/ui/node_modules" "${TARGET}/.cursor" "${TARGET}/assets"
  find "${TARGET}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
fi

echo "Ensuring Hermes profile livingcolor-pm..."
PYTHON_BIN="${HERMES_PYTHON:-}"
if [ -z "${PYTHON_BIN}" ] && [ -x "${HOME}/.hermes/hermes-agent/venv/bin/python" ]; then
  PYTHON_BIN="${HOME}/.hermes/hermes-agent/venv/bin/python"
fi
if [ -z "${PYTHON_BIN}" ]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [ -n "${PYTHON_BIN}" ]; then
  if ! PYTHONPATH="${TARGET}${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" -c "import yaml" 2>/dev/null; then
    echo "PyYAML not available in ${PYTHON_BIN}; livingcolor-pm profile will be created when Hermes starts"
  else
    PYTHONPATH="${TARGET}${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" -c "
import sys
sys.path.insert(0, '${TARGET}')
from lc_server.integrations.livingcolor_pm_profile import ensure_livingcolor_pm_profile
profile_dir = ensure_livingcolor_pm_profile()
print(f'livingcolor-pm profile ready at {profile_dir}')
"
  fi
else
  echo "python not found; livingcolor-pm profile will be created on first dashboard load"
fi

echo "Done. Restart the Hermes dashboard (not just the gateway) to load backend + UI changes:"
echo "  hermes dashboard --stop && hermes dashboard"
echo "  # or restart from the Hermes desktop app, then hard-refresh the browser (Cmd+Shift+R)"
