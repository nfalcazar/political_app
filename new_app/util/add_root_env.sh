#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TWO_LEVELS_UP="$(dirname "$SCRIPT_DIR")"
THREE_LEVELS_UP="$(dirname "$TWO_LEVELS_UP")"

export PROJ_ROOT="$THREE_LEVELS_UP"