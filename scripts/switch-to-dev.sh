#!/bin/bash
echo "Switching to development environment..."

# Update the .env file to use development
sed -i 's/PROD_OR_DEV=production/PROD_OR_DEV=development/' app/.env

echo "Switched to development environment!"
echo "Current database: $(grep 'DEV_SQL_URL' app/.env | cut -d'=' -f2)"
