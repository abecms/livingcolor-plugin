#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${HERMES_LIVINGCOLOR_PLUGIN_DIR:-$HOME/.hermes/plugins/livingcolor}"

echo "Syncing LivingColor plugin to ${TARGET}"

mkdir -p "${TARGET}"

rsync -a --delete \
  --exclude '.git/' \
  --exclude 'manim-video/' \
  --exclude 'ui/node_modules/' \
  --exclude '**/__pycache__/' \
  --exclude '.cursor/' \
  --exclude 'assets/' \
  "${ROOT}/" "${TARGET}/"

echo "Done. Restart Hermes to load backend + dashboard changes:"
echo "  hermes gateway restart"
