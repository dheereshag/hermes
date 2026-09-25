#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi
exec "$DIR/bin/hermes" "$@"
