#!/usr/bin/env python3
"""
Database migration script to rename columns to match timescale vector expectations.
This script renames:
- metadata_ -> metadata (in all tables)
- text -> contents (in claims table)

All data is preserved during the migration.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import logging

# Add the app directory to the Python path
app_dir = Path(__file__).parent.parent
sys.path.insert(0, str(app_dir))

# Load environment variables
env_file = app_dir / ".env"
load_dotenv(dotenv_path=env_file)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection from environment variables."""
    db_url = os.getenv("SQL_URL")
    if not db_url:
        raise ValueError("SQL_URL not found in environment variables")
    
    # Parse the URL to get connection parameters
    # SQL_URL format: postgresql://username:password@host:port/database
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "")
    
    # Split into parts
    auth_part, rest = db_url.split("@", 1)
    host_port_db = rest.split("/", 1)
    
    if len(host_port_db) != 2:
        raise ValueError("Invalid database URL format")
    
    host_port = host_port_db[0]
    database = host_port_db[1]
    
    if ":" in host_port:
        host, port = host_port.split(":", 1)
    else:
        host = host_port
        port = "5432"
    
    if ":" in auth_part:
        username, password = auth_part.split(":", 1)
    else:
        username = auth_part
        password = ""
    
    return psycopg2.connect(
        host=host,
        port=port,
        database=database,
        user=username,
        password=password
    )

def check_column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table."""
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = %s
    """, (table_name, column_name))
    return cursor.fetchone() is not None

def check_table_exists(cursor, table_name):
    """Check if a table exists."""
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_name = %s
    """, (table_name,))
    return cursor.fetchone() is not None

def migrate_columns():
    """Perform the column migration."""
    conn = get_db_connection()
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    try:
        logger.info("Starting database column migration...")
        
        # List of tables and their column mappings
        migrations = [
            # (table_name, old_column, new_column)
            ("canon_claims", "metadata_", "metadata"),
            ("claims", "metadata_", "metadata"),
            ("claims", "text", "contents"),
            ("sources", "metadata_", "metadata"),
            ("edges", "metadata_", "metadata"),
        ]
        
        for table_name, old_column, new_column in migrations:
            logger.info(f"Processing table: {table_name}")
            
            # Check if table exists
            if not check_table_exists(cursor, table_name):
                logger.warning(f"Table {table_name} does not exist, skipping...")
                continue
            
            # Check if old column exists
            if not check_column_exists(cursor, table_name, old_column):
                logger.warning(f"Column {old_column} does not exist in table {table_name}, skipping...")
                continue
            
            # Check if new column already exists
            if check_column_exists(cursor, table_name, new_column):
                logger.warning(f"Column {new_column} already exists in table {table_name}, skipping...")
                continue
            
            # Perform the column rename
            try:
                sql = f"ALTER TABLE {table_name} RENAME COLUMN {old_column} TO {new_column}"
                logger.info(f"Executing: {sql}")
                cursor.execute(sql)
                logger.info(f"Successfully renamed {old_column} to {new_column} in table {table_name}")
            except Exception as e:
                logger.error(f"Error renaming column {old_column} to {new_column} in table {table_name}: {e}")
                raise
        
        logger.info("Database migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def verify_migration():
    """Verify that the migration was successful."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        logger.info("Verifying migration...")
        
        # Check that new columns exist
        expected_columns = [
            ("canon_claims", "metadata"),
            ("canon_claims", "contents"),
            ("claims", "metadata"),
            ("claims", "contents"),
            ("sources", "metadata"),
            ("edges", "metadata"),
        ]
        
        for table_name, column_name in expected_columns:
            if check_column_exists(cursor, table_name, column_name):
                logger.info(f"✓ Column {column_name} exists in table {table_name}")
            else:
                logger.error(f"✗ Column {column_name} missing from table {table_name}")
        
        # Check that old columns don't exist
        old_columns = [
            ("canon_claims", "metadata_"),
            ("claims", "metadata_"),
            ("claims", "text"),
            ("sources", "metadata_"),
            ("edges", "metadata_"),
        ]
        
        for table_name, column_name in old_columns:
            if check_column_exists(cursor, table_name, column_name):
                logger.warning(f"⚠ Old column {column_name} still exists in table {table_name}")
            else:
                logger.info(f"✓ Old column {column_name} successfully removed from table {table_name}")
        
        logger.info("Migration verification completed!")
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    try:
        migrate_columns()
        verify_migration()
        logger.info("Migration and verification completed successfully!")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
