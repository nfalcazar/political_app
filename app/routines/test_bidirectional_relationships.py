"""
Test script for bidirectional relationship checking functionality.
"""

import logging
import sys
import os
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from database.sql_api import SqlStore

def test_bidirectional_relationship_checking():
    """Test the bidirectional relationship checking functions."""
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        sql_store = SqlStore()
        
        # Test 1: Check if relationship_exists_bidirectional works
        logger.info("Testing relationship_exists_bidirectional function...")
        
        # Create some test data (you'll need to have some claims in your database)
        # This is a simple test - you may need to adjust based on your actual data
        
        # Get a few claims from the database
        with sql_store.engine.connect() as connection:
            result = connection.execute("SELECT id FROM claims LIMIT 2")
            claims = result.fetchall()
            
            if len(claims) >= 2:
                claim_a_id = claims[0][0]
                claim_b_id = claims[1][0]
                
                logger.info(f"Testing with claims: {claim_a_id} and {claim_b_id}")
                
                # Test bidirectional check
                exists = sql_store.relationship_exists_bidirectional(claim_a_id, claim_b_id, 'claim')
                logger.info(f"Relationship exists between {claim_a_id} and {claim_b_id}: {exists}")
                
                # Test getting relationship details
                relationship = sql_store.get_relationship_between_entities(claim_a_id, claim_b_id, 'claim')
                if relationship:
                    logger.info(f"Relationship details: {relationship}")
                else:
                    logger.info("No relationship found between these claims")
                
                # Test reverse direction (should return same result)
                exists_reverse = sql_store.relationship_exists_bidirectional(claim_b_id, claim_a_id, 'claim')
                logger.info(f"Relationship exists (reverse check): {exists_reverse}")
                
                if exists != exists_reverse:
                    logger.warning("Bidirectional check is not symmetric!")
                else:
                    logger.info("Bidirectional check is working correctly")
                
            else:
                logger.warning("Not enough claims in database for testing")
        
        # Test 2: Test with canonical claims
        logger.info("Testing with canonical claims...")
        
        with sql_store.engine.connect() as connection:
            result = connection.execute("SELECT id FROM canon_claims LIMIT 2")
            canon_claims = result.fetchall()
            
            if len(canon_claims) >= 2:
                canon_a_id = canon_claims[0][0]
                canon_b_id = canon_claims[1][0]
                
                logger.info(f"Testing with canonical claims: {canon_a_id} and {canon_b_id}")
                
                exists = sql_store.relationship_exists_bidirectional(canon_a_id, canon_b_id, 'canonical_claim')
                logger.info(f"Relationship exists between canonical claims: {exists}")
                
                relationship = sql_store.get_relationship_between_entities(canon_a_id, canon_b_id, 'canonical_claim')
                if relationship:
                    logger.info(f"Canonical relationship details: {relationship}")
                else:
                    logger.info("No relationship found between these canonical claims")
        
        logger.info("Bidirectional relationship testing completed!")
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        raise

if __name__ == "__main__":
    test_bidirectional_relationship_checking()
