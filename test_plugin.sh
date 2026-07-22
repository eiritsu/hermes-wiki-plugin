#!/bin/bash
# Run plugin tests with the correct Python (Hermes venv)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PYTHON="$HERMES_HOME/hermes-agent/venv/bin/python3"

if [ ! -f "$PYTHON" ]; then
  echo "ERROR: Hermes venv not found at $PYTHON"
  exit 1
fi

cd "$SCRIPT_DIR"
exec "$PYTHON" "$@"
