#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$repository_root/.venv/bin/python" "$repository_root/scripts/run-development.py" "$@"
