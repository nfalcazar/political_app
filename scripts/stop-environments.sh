#!/bin/bash
echo "Stopping both Production and Development environments..."
cd docker
docker-compose down
echo "Both environments stopped!"


