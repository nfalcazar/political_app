#!/bin/bash
echo "Current environment: $(grep 'PROD_OR_DEV' app/.env | cut -d'=' -f2)"
echo "Production DB: $(grep 'PROD_SQL_URL' app/.env | cut -d'=' -f2)"
echo "Development DB: $(grep 'DEV_SQL_URL' app/.env | cut -d'=' -f2)"
