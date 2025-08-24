import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

class EnvironmentManager:
    def __init__(self, env: Optional[str] = None):
        """
        Initialize environment manager.
        
        Args:
            env: Environment name ('production', 'development', or None for auto-detect)
        """
        # Load environment variables from .env file
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
        else:
            print(f"Warning: Environment file {env_path} not found.")
        
        # Determine which environment to use
        if env:
            self.env = env
        else:
            self.env = os.getenv('PROD_OR_DEV', 'development')
        
        # Validate environment
        if self.env not in ['production', 'development']:
            raise ValueError(f"Invalid environment: {self.env}. Must be 'production' or 'development'")
        
        print(f"Using {self.env} environment")
    
    def get_db_url(self) -> str:
        """Get the database URL for the current environment."""
        if self.env == 'production':
            url = os.getenv('PROD_SQL_URL')
        else:
            url = os.getenv('DEV_SQL_URL')
        
        if not url:
            raise ValueError(f"{self.env.upper()}_SQL_URL not found in environment variables")
        
        return url
    
    def get_timescale_url(self) -> str:
        """Get the TimescaleDB service URL for the current environment."""
        if self.env == 'production':
            url = os.getenv('PROD_TIMESCALE_SERVICE_URL')
        else:
            url = os.getenv('DEV_TIMESCALE_SERVICE_URL')
        
        if not url:
            raise ValueError(f"{self.env.upper()}_TIMESCALE_SERVICE_URL not found in environment variables")
        
        return url
    
    def get_prod_db_url(self) -> str:
        """Get the production database URL (for copying operations)."""
        url = os.getenv('PROD_SQL_URL')
        if not url:
            raise ValueError("PROD_SQL_URL not found in environment variables")
        return url
    
    def get_dev_db_url(self) -> str:
        """Get the development database URL (for copying operations)."""
        url = os.getenv('DEV_SQL_URL')
        if not url:
            raise ValueError("DEV_SQL_URL not found in environment variables")
        return url
    
    def get_prod_timescale_url(self) -> str:
        """Get the production TimescaleDB URL (for copying operations)."""
        url = os.getenv('PROD_TIMESCALE_SERVICE_URL')
        if not url:
            raise ValueError("PROD_TIMESCALE_SERVICE_URL not found in environment variables")
        return url
    
    def get_dev_timescale_url(self) -> str:
        """Get the development TimescaleDB URL (for copying operations)."""
        url = os.getenv('DEV_TIMESCALE_SERVICE_URL')
        if not url:
            raise ValueError("DEV_TIMESCALE_SERVICE_URL not found in environment variables")
        return url
    
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.env == 'development'
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.env == 'production'
    
    def get_current_env(self) -> str:
        """Get the current environment name."""
        return self.env
    
    def switch_environment(self, new_env: str):
        """Switch to a different environment."""
        if new_env not in ['production', 'development']:
            raise ValueError(f"Invalid environment: {new_env}")
        
        self.env = new_env
        print(f"Switched to {self.env} environment")
