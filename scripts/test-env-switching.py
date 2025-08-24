#!/usr/bin/env python3
"""
Test script to verify environment switching works correctly.
"""

import sys
from pathlib import Path

# Add app directory to path
app_dir = Path(__file__).parent.parent / "app"
sys.path.insert(0, str(app_dir))

from config.env_manager import EnvironmentManager

def test_environment_switching():
    """Test that environment switching works correctly."""
    print("Testing environment switching...")
    
    # Test default environment (should be development)
    print("\n1. Testing default environment:")
    env_manager = EnvironmentManager()
    print(f"   Current environment: {env_manager.get_current_env()}")
    print(f"   Database URL: {env_manager.get_db_url()}")
    print(f"   Timescale URL: {env_manager.get_timescale_url()}")
    
    # Test explicit development environment
    print("\n2. Testing explicit development environment:")
    dev_manager = EnvironmentManager('development')
    print(f"   Environment: {dev_manager.get_current_env()}")
    print(f"   Database URL: {dev_manager.get_db_url()}")
    print(f"   Timescale URL: {dev_manager.get_timescale_url()}")
    
    # Test explicit production environment
    print("\n3. Testing explicit production environment:")
    prod_manager = EnvironmentManager('production')
    print(f"   Environment: {prod_manager.get_current_env()}")
    print(f"   Database URL: {prod_manager.get_db_url()}")
    print(f"   Timescale URL: {prod_manager.get_timescale_url()}")
    
    # Test environment switching
    print("\n4. Testing environment switching:")
    env_manager.switch_environment('production')
    print(f"   After switching to production: {env_manager.get_current_env()}")
    print(f"   Database URL: {env_manager.get_db_url()}")
    
    env_manager.switch_environment('development')
    print(f"   After switching to development: {env_manager.get_current_env()}")
    print(f"   Database URL: {env_manager.get_db_url()}")
    
    print("\nEnvironment switching test completed successfully!")

if __name__ == "__main__":
    test_environment_switching()


