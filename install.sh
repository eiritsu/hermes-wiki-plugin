#!/usr/bin/env bash
# hermes-wiki plugin installer
# Usage: bash install.sh

set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
BACKEND_SRC="$(cd "$(dirname "$0")/backend" && pwd)"
DESKTOP_SRC="$(cd "$(dirname "$0")/desktop" && pwd)"
PATCH_FILE="$(cd "$(dirname "$0")" && pwd)/gateway-rpc.patch"

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

# Gateway RPC patch (needed until PR #66874 is merged upstream)
HERMES_AGENT="$HERMES_HOME/hermes-agent"
if [ -d "$HERMES_AGENT/.git" ] && [ -f "$PATCH_FILE" ]; then
  echo ""
  echo "Checking gateway RPC patch..."
  # Check if already applied (register_rpc exists in plugins.py)
  if grep -q "register_rpc" "$HERMES_AGENT/hermes_cli/plugins.py" 2>/dev/null; then
    echo "  Gateway RPC patch already applied."
  else
    echo "  Applying gateway RPC patch to $HERMES_AGENT..."
    if (cd "$HERMES_AGENT" && git apply --check "$PATCH_FILE" 2>/dev/null); then
      (cd "$HERMES_AGENT" && git apply "$PATCH_FILE")
      echo "  Patch applied successfully."
      echo "  Restart Hermes gateway to activate wiki RPC."
    else
      echo "  ⚠ Patch could not be applied automatically."
      echo "  This may happen after 'hermes update' changes the source."
      echo "  Manual fix: cd $HERMES_AGENT && git apply $PATCH_FILE"
      echo "  Or wait for PR #66874 to be merged upstream."
    fi
  fi
fi

# Check config and enable hermes-wiki plugin + toolset
CONFIG="$HERMES_HOME/config.yaml"
if [ -f "$CONFIG" ]; then
  if ! grep -q "hermes-wiki" "$CONFIG"; then
    echo ""
    echo "  Add 'hermes-wiki' to plugins.enabled in $CONFIG"
  fi
  # Ensure wiki toolset is enabled so wiki_search is available to the agent
  python3 -c "
import yaml
cfg_path = '$CONFIG'
with open(cfg_path) as f:
    cfg = yaml.safe_load(f) or {}
toolsets = cfg.get('toolsets', [])
changed = False
# Add wiki toolset (plugin-provided, contains wiki_search)
if isinstance(toolsets, list) and 'wiki' not in toolsets:
    toolsets.append('wiki')
    changed = True
# Remove hermes-wiki if present (triggers platform adapter bug, not a real toolset)
if isinstance(toolsets, list) and 'hermes-wiki' in toolsets:
    toolsets.remove('hermes-wiki')
    changed = True
# Remove memory if we previously added it (wiki_search is no longer there)
if isinstance(toolsets, list) and 'memory' in toolsets and 'memory' not in ('hermes-cli',):
    # Only remove if it was added by us (not by user intentionally)
    pass  # keep memory — user may have other reasons
if changed:
    cfg['toolsets'] = toolsets
    with open(cfg_path, 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
    print('  Enabled wiki toolset (wiki_search available)')
else:
    print('  wiki toolset already enabled')
" 2>/dev/null || echo "  (toolset config skipped — manual: add 'wiki' to toolsets in config.yaml)"
fi

echo ""
echo "Done. Restart Hermes to activate."
