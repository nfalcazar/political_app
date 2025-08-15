#!/usr/bin/env python3
"""
Test script to run source resolution for a specific source ID
"""

import json
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
current_file = Path(__file__)
env_file = current_file.parent.parent / ".env"
load_dotenv(dotenv_path=env_file)
PROJ_ROOT = Path(os.environ["PROJ_ROOT"])

# Import your existing modules
sys.path.append(str(PROJ_ROOT / "app"))

from database.sql_api import SqlStore
from util.ai_ext_calls import OpenAiSync
from routines.resolve_sources import generate_search_query, get_claim_for_source

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_specific_source(source_id: str):
    """Test source resolution for a specific source ID"""
    
    # Initialize components
    sql_store = SqlStore()
    ai_client = OpenAiSync(provider="openai")
    
    # Get the specific source
    try:
        sources = sql_store.get_data_by_field('sources', 'id', source_id)
        if not sources:
            logger.error(f"Source {source_id} not found")
            return
        source = sources[0]  # Get the first (and should be only) result
        if not source:
            logger.error(f"Source {source_id} not found")
            return
        
        logger.info(f"Testing source: {source_id}")
        logger.info(f"Source description: {source.get('description', 'N/A')}")
        
        # Get associated claim
        claim = get_claim_for_source(sql_store, source_id)
        if not claim:
            logger.error(f"No claim found for source {source_id}")
            return
        
        logger.info(f"Associated claim: {claim.get('text', 'N/A')}")
        
        # Generate search query
        logger.info("Generating search query...")
        query_dict = generate_search_query(ai_client, claim, source)
        
        logger.info(f"Generated query: {json.dumps(query_dict, indent=2)}")
        
        # Check for site restrictions in the query
        query_text = query_dict.get('q', '')
        if 'site:' in query_text:
            logger.info(f"Site restriction found in query: {query_text}")
        else:
            logger.info("No site restriction in query")
        
        # Test the actual search functionality
        logger.info("Testing search functionality...")
        from routines.resolve_sources import perform_google_search
        
        source_type = source.get('metadata_', {}).get('source_type', '') if isinstance(source.get('metadata_'), dict) else ''
        search_metadata = perform_google_search(query_dict, source_type=source_type)
        
        logger.info(f"Search attempt: {search_metadata.get('search_attempt', 'unknown')}")
        logger.info(f"Total results: {search_metadata.get('total_results', 0)}")
        logger.info(f"Items found: {len(search_metadata.get('items', []))}")
        
        if search_metadata.get('items'):
            logger.info("Top result:")
            top_result = search_metadata['items'][0]
            logger.info(f"  Title: {top_result.get('title', 'N/A')}")
            logger.info(f"  Link: {top_result.get('link', 'N/A')}")
        
    except Exception as e:
        logger.error(f"Error testing source {source_id}: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    source_id = "208d6708-78d2-11f0-ab68-19f98248ab1b"
    test_specific_source(source_id)
