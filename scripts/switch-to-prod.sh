#!/bin/bash
echo "Switching to production environment..."

# Update the .env file to use production
sed -i 's/PROD_OR_DEV=development/PROD_OR_DEV=production/' app/.env

echo "Switched to production environment!"
echo "Current database: $(grep 'PROD_SQL_URL' app/.env | cut -d'=' -f2)"
