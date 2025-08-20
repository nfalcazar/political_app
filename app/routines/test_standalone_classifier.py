"""
Test script for the standalone claim relationship classifier.
"""

import logging
import sys
import os
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from routines.claim_relationship_classifier import ClaimRelationshipClassifier

def test_classmethod_classifier():
    """Test the classmethod relationship classifier."""
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        # Test 1: Process only canonical claims
        logger.info("Testing canonical claims processing...")
        stats1 = ClaimRelationshipClassifier.classify_claim_relationships("canon_claims", force_reprocess=False)
        logger.info(f"Canonical claims test results: {stats1}")
        
        # Test 2: Process only regular claims
        logger.info("Testing regular claims processing...")
        stats2 = ClaimRelationshipClassifier.classify_claim_relationships("claims", force_reprocess=False)
        logger.info(f"Regular claims test results: {stats2}")
        
        # Test 3: Process both types
        logger.info("Testing both claims types processing...")
        stats3 = ClaimRelationshipClassifier.classify_claim_relationships("both", force_reprocess=False)
        logger.info(f"Both types test results: {stats3}")
        
        # Test 4: Show class configuration
        logger.info(f"Class configuration:")
        logger.info(f"  Similarity threshold: {ClaimRelationshipClassifier.SIMILARITY_THRESHOLD}")
        logger.info(f"  Max similar claims: {ClaimRelationshipClassifier.MAX_SIMILAR_CLAIMS}")
        logger.info(f"  Batch size: {ClaimRelationshipClassifier.BATCH_SIZE}")
        logger.info(f"  LLM provider: {ClaimRelationshipClassifier.LLM_PROVIDER}")
        
        logger.info("All classmethod classifier tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        raise

if __name__ == "__main__":
    test_classmethod_classifier()
