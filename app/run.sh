#!/bin/bash

source ./util/add_root_env.sh
source $PROJ_ROOT/app/venv/bin/activate
python $PROJ_ROOT/app/pol_app.py
