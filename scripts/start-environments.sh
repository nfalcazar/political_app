#!/bin/bash
echo "Starting both Production and Development environments..."

# Start both databases
cd docker
docker-compose up -d

# Wait for databases to be ready
echo "Waiting for databases to be ready..."
sleep 15

echo "Both environments started!"
echo "Production database: postgresql://postgres:password@localhost:5432/postgres"
echo "Development database: postgresql://postgres:password@localhost:5433/postgres"


