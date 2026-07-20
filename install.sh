#!/usr/bin/env bash
# hermes-wiki plugin installer
# Usage: bash install.sh

set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
BACKEND_SRC="$(cd "$(dirname "$0")/backend" && pwd)"
DESKTOP_SRC="$(cd "$(dirname "$0")/desktop" && pwd)"

BACKEND_DST="$HERMES_HOME/plugins/hermes_wiki"
DESKTOP_DST="$HERMES_HOME/desktop-plugins/wiki"

echo "Installing hermes-wiki plugin..."
echo ""

# Backend plugin
mkdir -p "$BACKEND_DST/prompts"
for f in plugin.yaml __init__.py wiki_store.py wiki_builder.py wiki_rpc.py; do
  cp "$BACKEND_SRC/$f" "$BACKEND_DST/"
done
cp "$BACKEND_SRC/prompts/default.md" "$BACKEND_DST/prompts/"
echo "  Backend  -> $BACKEND_DST"

# Desktop plugin
mkdir -p "$DESKTOP_DST"
cp "$DESKTOP_SRC/plugin.js" "$DESKTOP_DST/"
echo "  Desktop  -> $DESKTOP_DST"

# Check config
CONFIG="$HERMES_HOME/config.yaml"
if [ -f "$CONFIG" ]; then
  if ! grep -q "hermes-wiki" "$CONFIG"; then
    echo ""
    echo "  Add 'hermes-wiki' to plugins.enabled in $CONFIG"
  fi
fi

echo ""
echo "Done. Restart Hermes to activate."
