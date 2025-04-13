#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TWO_LEVELS_UP="$(dirname "$SCRIPT_DIR")"

export PROJ_ROOT="$TWO_LEVELS_UP"
python $PROJ_ROOT/app/pol_app.py
