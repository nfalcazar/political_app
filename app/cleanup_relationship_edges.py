#!/usr/bin/env python3
"""
Script to clean up all relationship edges from the database.
This removes all edges with relationship types: supports, opposes, neutral, uncertain
so that the relationship classification can be rerun with the new categories.
"""

import sys
import os
import logging
from pathlib import Path

# Add the app directory to the Python path
app_dir = Path(__file__).parent
sys.path.insert(0, str(app_dir))

from database.sql_api import SqlStore
from routines.relationship_config import SUPPORTED_RELATIONSHIP_TYPES

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_relationship_edges():
    """Remove all edges with relationship types from the database."""
    
    # Add 'uncertain' to the list since it was previously used
    relationship_types_to_remove = SUPPORTED_RELATIONSHIP_TYPES + ['uncertain']
    
    logger.info(f"Starting cleanup of relationship edges...")
    logger.info(f"Relationship types to remove: {relationship_types_to_remove}")
    
    try:
        # Initialize database connection
        sql_store = SqlStore()
        
        # Get count of edges to be removed
        with sql_store.engine.connect() as connection:
            from sqlalchemy import text
            
            count_query = text("""
                SELECT COUNT(*) FROM edges 
                WHERE relationship_type IN :relationship_types
            """)
            
            result = connection.execute(count_query, {
                'relationship_types': tuple(relationship_types_to_remove)
            })
            count = result.fetchone()[0]
            
            logger.info(f"Found {count} edges to remove")
            
            if count == 0:
                logger.info("No relationship edges found to remove. Database is already clean.")
                return
            
            # Confirm with user
            response = input(f"Are you sure you want to remove {count} relationship edges? (yes/no): ")
            if response.lower() != 'yes':
                logger.info("Cleanup cancelled by user.")
                return
            
            # Remove the edges
            delete_query = text("""
                DELETE FROM edges 
                WHERE relationship_type IN :relationship_types
            """)
            
            result = connection.execute(delete_query, {
                'relationship_types': tuple(relationship_types_to_remove)
            })
            
            connection.commit()
            
            logger.info(f"Successfully removed {result.rowcount} relationship edges from the database.")
            
            # Verify cleanup
            verify_query = text("""
                SELECT COUNT(*) FROM edges 
                WHERE relationship_type IN :relationship_types
            """)
            
            result = connection.execute(verify_query, {
                'relationship_types': tuple(relationship_types_to_remove)
            })
            remaining_count = result.fetchone()[0]
            
            if remaining_count == 0:
                logger.info("✅ Cleanup verified: No relationship edges remain in the database.")
            else:
                logger.warning(f"⚠️  Warning: {remaining_count} relationship edges still remain in the database.")
                
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        sys.exit(1)

def show_edge_statistics():
    """Show current edge statistics before cleanup."""
    
    logger.info("Current edge statistics:")
    
    try:
        sql_store = SqlStore()
        
        with sql_store.engine.connect() as connection:
            from sqlalchemy import text
            
            # Count by relationship type
            stats_query = text("""
                SELECT relationship_type, COUNT(*) as count 
                FROM edges 
                GROUP BY relationship_type 
                ORDER BY count DESC
            """)
            
            result = connection.execute(stats_query)
            
            for row in result:
                logger.info(f"  {row[0]}: {row[1]} edges")
                
            # Total count
            total_query = text("SELECT COUNT(*) FROM edges")
            total = connection.execute(total_query).fetchone()[0]
            logger.info(f"  Total edges: {total}")
            
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("RELATIONSHIP EDGES CLEANUP SCRIPT")
    print("=" * 60)
    print()
    print("This script will remove all edges with relationship types:")
    print("  - supports")
    print("  - opposes") 
    print("  - neutral")
    print("  - uncertain (previously used)")
    print()
    print("This will allow you to rerun relationship classification")
    print("with the updated categories and logic.")
    print()
    
    # Show current statistics
    show_edge_statistics()
    print()
    
    # Run cleanup
    cleanup_relationship_edges()
    
    print()
    print("=" * 60)
    print("Cleanup complete!")
    print("=" * 60)
