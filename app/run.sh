#!/bin/bash
# TODO: How to pass protect / safe way to store DB info
# TODO: Add interface for Keyring

source ./util/add_root_env.sh
source ~/Keyring/add_keyring_env.sh
TIMESCALE_SERVICE_URL=postgres://postgres:password@localhost:5432/postgres

source $PROJ_ROOT/app/venv/bin/activate
python $PROJ_ROOT/app/pol_app.py
