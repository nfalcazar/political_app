# Environment Management Scripts

This directory contains scripts for managing production and development database environments.

## Overview

The system uses a single `.env` file in the `app` directory with both production and development database URLs, controlled by a `PROD_OR_DEV` environment variable.

## Database URLs

- **Production**: `postgresql://postgres:password@localhost:5432/postgres`
- **Development**: `postgresql://postgres:password@localhost:5433/postgres`

## Scripts

### Environment Switching

- `switch-to-prod.sh` - Switch to production environment
- `switch-to-dev.sh` - Switch to development environment  
- `show-env.sh` - Show current environment and database URLs

### Database Management

- `start-environments.sh` - Start both production and development databases
- `stop-environments.sh` - Stop both databases

### Data Operations

- `copy-prod-to-dev.py` - Copy production data to development database
- `test-env-switching.py` - Test environment switching functionality

## Usage Examples

### Switch Environments

```bash
# Switch to production
./scripts/switch-to-prod.sh

# Switch to development
./scripts/switch-to-dev.sh

# Check current environment
./scripts/show-env.sh
```

### Start/Stop Databases

```bash
# Start both databases
./scripts/start-environments.sh

# Stop both databases
./scripts/stop-environments.sh
```

### Copy Production Data to Development

```bash
# Copy all data
python scripts/copy-prod-to-dev.py --mode full

# Copy recent data (last 7 days)
python scripts/copy-prod-to-dev.py --mode recent --days 7

# Copy specific claims
python scripts/copy-prod-to-dev.py --mode specific --claim-ids claim1 claim2

# Copy without embeddings (faster)
python scripts/copy-prod-to-dev.py --mode full --no-embeddings

# Copy without relationships
python scripts/copy-prod-to-dev.py --mode full --no-relationships
```

### Run Your Application

```bash
# Activate virtual environment
cd app && source venv/bin/activate && cd ..

# Run in current environment (based on .env file)
python app/pol_app.py

# Test environment switching
python scripts/test-env-switching.py
```

## How It Works

1. **Single .env File**: Located in `app/.env`, contains both production and development URLs
2. **Environment Manager**: Python class that reads the `PROD_OR_DEV` variable
3. **Database APIs**: `sql_api.py` and `vector_api.py` use the environment manager
4. **Shell Scripts**: Update the `app/.env` file to switch environments

## Benefits

- **Cost Efficient**: Copy production data instead of regenerating embeddings
- **Safe Testing**: Test new configurations without affecting production
- **Easy Switching**: Simple scripts to change environments
- **Single Configuration**: All URLs in one place
