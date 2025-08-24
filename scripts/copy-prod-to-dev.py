#!/usr/bin/env python3
"""
Script to copy production data to development database.
This copies the hard data (references, citations, embeddings) without regenerating them.
"""

import sys
from pathlib import Path
import argparse
import logging
from datetime import datetime

# Add app directory to path
app_dir = Path(__file__).parent.parent / "app"
sys.path.insert(0, str(app_dir))

import psycopg2
from sqlalchemy import create_engine, text
import pandas as pd
from config.env_manager import EnvironmentManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataCopier:
    def __init__(self):
        # Initialize environment manager
        self.env_manager = EnvironmentManager()
        
        # Production database connection
        self.prod_engine = create_engine(self.env_manager.get_prod_db_url())
        
        # Development database connection
        self.dev_engine = create_engine(self.env_manager.get_dev_db_url())
    
    def copy_table_data(self, table_name, where_clause=None, limit=None):
        """
        Copy data from production to development table.
        
        Args:
            table_name: Name of the table to copy
            where_clause: Optional WHERE clause to filter data
            limit: Optional limit on number of rows to copy
        """
        logger.info(f"Copying data from {table_name}...")
        
        # Build query
        query = f"SELECT * FROM {table_name}"
        if where_clause:
            query += f" WHERE {where_clause}"
        if limit:
            query += f" LIMIT {limit}"
        
        # Read from production
        try:
            df = pd.read_sql(query, self.prod_engine)
            logger.info(f"Read {len(df)} rows from production {table_name}")
        except Exception as e:
            logger.error(f"Error reading from production {table_name}: {e}")
            return False
        
        if df.empty:
            logger.warning(f"No data found in production {table_name}")
            return True
        
        # Clear development table (optional - you might want to append instead)
        try:
            with self.dev_engine.connect() as conn:
                conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
                conn.commit()
            logger.info(f"Cleared development {table_name}")
        except Exception as e:
            logger.error(f"Error clearing development {table_name}: {e}")
            return False
        
        # Write to development
        try:
            df.to_sql(table_name, self.dev_engine, if_exists='append', index=False)
            logger.info(f"Successfully copied {len(df)} rows to development {table_name}")
            return True
        except Exception as e:
            logger.error(f"Error writing to development {table_name}: {e}")
            return False
    
    def copy_claims_and_sources(self, include_embeddings=True, include_relationships=True):
        """
        Copy claims, sources, and related data from production to development.
        
        Args:
            include_embeddings: Whether to copy embedding data
            include_relationships: Whether to copy relationship data
        """
        logger.info("Starting production to development data copy...")
        
        # Core data tables to copy
        core_tables = [
            'claims',
            'canon_claims', 
            'sources',
            'facts'
        ]
        
        # Copy core tables
        for table in core_tables:
            success = self.copy_table_data(table)
            if not success:
                logger.error(f"Failed to copy {table}")
                return False
        
        # Copy embeddings if requested
        if include_embeddings:
            embedding_tables = [
                'claims_embedding',
                'canon_claims_embedding'
            ]
            for table in embedding_tables:
                success = self.copy_table_data(table)
                if not success:
                    logger.warning(f"Failed to copy {table} - embeddings may need regeneration")
        
        # Copy relationships if requested
        if include_relationships:
            relationship_tables = [
                'edges',
                'claim_relationships'
            ]
            for table in relationship_tables:
                success = self.copy_table_data(table)
                if not success:
                    logger.warning(f"Failed to copy {table} - relationships may need regeneration")
        
        logger.info("Production to development data copy completed!")
        return True
    
    def copy_recent_data(self, days=7):
        """
        Copy only recent data from production to development.
        
        Args:
            days: Number of days of recent data to copy
        """
        logger.info(f"Copying recent data (last {days} days) from production to development...")
        
        # Copy recent claims
        self.copy_table_data('claims', 
                           where_clause=f"created_at >= NOW() - INTERVAL '{days} days'")
        
        # Copy recent sources
        self.copy_table_data('sources', 
                           where_clause=f"created_at >= NOW() - INTERVAL '{days} days'")
        
        # Copy related embeddings and relationships
        # (You'll need to adjust this based on your actual table structure)
        
        logger.info("Recent data copy completed!")
    
    def copy_specific_claims(self, claim_ids):
        """
        Copy specific claims and their related data.
        
        Args:
            claim_ids: List of claim IDs to copy
        """
        logger.info(f"Copying specific claims: {claim_ids}")
        
        # Convert list to SQL IN clause
        ids_str = ','.join([f"'{id}'" for id in claim_ids])
        
        # Copy specific claims
        self.copy_table_data('claims', where_clause=f"id IN ({ids_str})")
        
        # Copy related sources, embeddings, etc.
        # (Adjust based on your actual relationships)
        
        logger.info("Specific claims copy completed!")

def main():
    parser = argparse.ArgumentParser(description='Copy production data to development')
    parser.add_argument('--mode', choices=['full', 'recent', 'specific'], 
                       default='full', help='Copy mode')
    parser.add_argument('--days', type=int, default=7,
                       help='Number of days for recent copy mode')
    parser.add_argument('--claim-ids', nargs='+',
                       help='Specific claim IDs to copy')
    parser.add_argument('--no-embeddings', action='store_true',
                       help='Skip copying embeddings')
    parser.add_argument('--no-relationships', action='store_true',
                       help='Skip copying relationships')
    
    args = parser.parse_args()
    
    copier = DataCopier()
    
    if args.mode == 'full':
        copier.copy_claims_and_sources(
            include_embeddings=not args.no_embeddings,
            include_relationships=not args.no_relationships
        )
    elif args.mode == 'recent':
        copier.copy_recent_data(args.days)
    elif args.mode == 'specific':
        if not args.claim_ids:
            logger.error("Specific mode requires --claim-ids")
            return
        copier.copy_specific_claims(args.claim_ids)

if __name__ == "__main__":
    main()


