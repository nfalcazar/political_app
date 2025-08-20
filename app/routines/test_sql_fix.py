"""
Test script to verify the SQL query fix works correctly.
"""

import logging
import sys
import os
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from routines.claim_relationship_classifier import ClaimRelationshipClassifier

def test_sql_fix():
    """Test that the SQL queries work correctly after the fix."""
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Testing SQL query fix...")
        
        # Test the main function - this should not crash with SQL errors
        stats = ClaimRelationshipClassifier.classify_claim_relationships("both", force_reprocess=False)
        
        logger.info(f"SQL fix test completed successfully: {stats}")
        
        # The test passes if we don't get SQL execution errors
        # Even if no data is found, that's expected if the database is empty
        
    except Exception as e:
        logger.error(f"SQL fix test failed with error: {e}")
        raise

if __name__ == "__main__":
    test_sql_fix()
