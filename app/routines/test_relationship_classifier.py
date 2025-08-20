"""
Test script for the Claim Relationship Classifier module.
"""

import logging
import sys
import os
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from claim_relationship_classifier import ClaimRelationshipClassifier

def test_relationship_classifier():
    """Test the relationship classifier with different configurations."""
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        # Test 4: Test with custom parameters
        logger.info("Testing funct call...")
        stats4 = ClaimRelationshipClassifier.classify_claim_relationships("both", force_reprocess=False)
        logger.info(f"Custom parameters test results: {stats4}")
        
        logger.info("All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        raise

if __name__ == "__main__":
    test_relationship_classifier()
