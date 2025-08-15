"""
Source Resolution Module

This module provides functions to resolve unresolved sources using LLM-generated
Google Custom Search queries. It's designed to be called on a schedule from pol_app.py.

Usage:
    from routines.resolve_sources import resolve_unresolved_sources
    
    # Call directly
    resolve_unresolved_sources()
"""

import json
import logging
import os
import requests
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
current_file = Path(__file__)
env_file = current_file.parent.parent / ".env"
load_dotenv(dotenv_path=env_file)
PROJ_ROOT = Path(os.environ["PROJ_ROOT"])

# Import your existing modules
import sys
sys.path.append(str(PROJ_ROOT / "app"))

from database.sql_api import SqlStore
from util.ai_ext_calls import OpenAiSync
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

logger = logging.getLogger(__name__)


def resolve_unresolved_sources():
    """
    Main function to resolve all unresolved sources.
    This is the entry point that gets called by the scheduler.
    """
    try:
        logger.info("Starting source resolution run")
        
        # Initialize components
        sql_store = SqlStore()
        ai_client = OpenAiSync(provider="openai")  # Use faster OpenAI for queries
        
        # Google Custom Search API credentials are now handled internally in perform_google_search
        
        # Get unresolved sources
        unresolved_sources = get_unresolved_sources(sql_store)
        
        if unresolved_sources:
            logger.info(f"Found {len(unresolved_sources)} unresolved sources to process")
            
            # Process in batches with parallel LLM query generation
            batch_size = 20  # Process 20 sources at a time
            max_workers = 7  # Number of parallel LLM workers
            
            for i in range(0, len(unresolved_sources), batch_size):
                batch = unresolved_sources[i:i + batch_size]
                logger.info(f"Processing batch {i//batch_size + 1}/{(len(unresolved_sources) + batch_size - 1)//batch_size}")
                process_source_batch(batch, sql_store, ai_client, max_workers=max_workers)
                
                # Rate limiting between batches
                if i + batch_size < len(unresolved_sources):
                    logger.info("Waiting 10 seconds before next batch...")
                    time.sleep(10)
        else:
            logger.debug("No unresolved sources found")
            
    except Exception as e:
        logger.error(f"Error in source resolution: {e}")


def get_unresolved_sources(sql_store: SqlStore) -> List[Dict]:
    """
    Get all sources with match_status = 'unresolved' that haven't been processed before
    
    Args:
        sql_store: SqlStore instance
        
    Returns:
        List of source dictionaries
    """
    try:
        # Use SQL API method to query sources by metadata field
        sources = sql_store.get_sources_by_metadata_field('$.match_status', 'unresolved', limit=50)
        
        # Filter out sources that have already been processed (have search_results)
        unprocessed_sources = []
        for source in sources:
            if not is_source_processed(source):
                unprocessed_sources.append(source)
            else:
                logger.debug(f"Skipping already processed source: {source['id']}")
        
        logger.info(f"Found {len(unprocessed_sources)} unprocessed sources out of {len(sources)} unresolved sources")
        return unprocessed_sources
                
    except Exception as e:
        logger.error(f"Error querying unresolved sources: {e}")
        return []


def is_source_processed(source: Dict) -> bool:
    """
    Check if a source has already been processed (has search_results in metadata)
    
    Args:
        source: Source dictionary
        
    Returns:
        True if source has been processed, False otherwise
    """
    metadata_raw = source.get('metadata_', '{}')
    if isinstance(metadata_raw, dict):
        metadata = metadata_raw
    else:
        try:
            metadata = json.loads(metadata_raw)
        except json.JSONDecodeError:
            metadata = {}
    
    return 'search_results' in metadata


def get_claim_for_source(sql_store: SqlStore, source_id: str) -> Optional[Dict]:
    """
    Get a claim that cites this source
    
    Args:
        sql_store: SqlStore instance
        source_id: The source ID to find claims for
        
    Returns:
        Dictionary containing claim information, or None if not found
    """
    try:
        # Query for claims that cite this source via edges table
        from sqlalchemy import text
        query = text("""
        SELECT c.* FROM claims c
        JOIN edges e ON e.src_id = c.id
        WHERE e.dest_id = :source_id 
        AND e.relationship_type = 'cites'
        LIMIT 1
        """)
        
        with sql_store.engine.connect() as connection:
            result = connection.execute(query, {"source_id": source_id})
            row = result.fetchone()
            
            if row:
                columns = result.keys()
                return dict(zip(columns, row))
            else:
                return None
                
    except Exception as e:
        logger.error(f"Error finding claim for source {source_id}: {e}")
        return None


def generate_search_query_batch(ai_client: OpenAiSync, claim: Dict, source: Dict) -> Dict:
    """
    Generate a Google Custom Search query using LLM (for batch processing)
    
    Args:
        ai_client: OpenAiSync instance
        claim: Dictionary containing claim information
        source: Dictionary containing source information
        
    Returns:
        Dictionary containing search query parameters (q, orTerms) and source info
    """
    return _generate_search_query_internal(ai_client, claim, source)


def _generate_search_query_internal(ai_client: OpenAiSync, claim: Dict, source: Dict) -> Dict:
    """
    Internal function to generate search query (without rate limiting logic)
    """
    try:
        # Load the system prompt from file
        prompt_file_path = PROJ_ROOT / "app" / "prompts" / "goog_search.txt"
        with open(prompt_file_path, 'r') as f:
            sys_prompt = f.read()
        
        # Parse metadata from source
        metadata_raw = source.get('metadata_', '{}')
        if isinstance(metadata_raw, dict):
            source_metadata = metadata_raw
        else:
            try:
                source_metadata = json.loads(metadata_raw)
            except json.JSONDecodeError as json_error:
                logger.error(f"Error parsing source metadata: {json_error}")
                source_metadata = {}
        
        # Build context for LLM
        claim_text = claim.get('text', '') if claim else ''
        source_title = source.get('description', '')
        source_type = source_metadata.get('source_type', '')
        publisher = source_metadata.get('publisher_or_court', '')
        existing_search_queries = source_metadata.get('search_query', [])
        
        # Create the user query in the specified format
        user_query = f"##Claim##\n{claim_text}\n\n##Source metadata##\nTitle/Description: {source_title}\nType: {source_type}\nPublisher/Court: {publisher}\n\n##Potential Keywords/Phrases##\n{existing_search_queries}"

        # Get response from LLM using system and user prompts
        response = ai_client.query(user_prompt=user_query, sys_prompt=sys_prompt)
        
        # Check if response is already a dict
        if isinstance(response, dict):
            query_dict = response
        else:
            # Clean up the response and parse JSON
            cleaned_response = response.strip()
            # Remove any markdown formatting
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            # Parse the JSON response
            try:
                query_dict = json.loads(cleaned_response.strip())
            except json.JSONDecodeError as json_error:
                logger.error(f"JSON decode error: {json_error}")
                logger.error(f"Failed to parse response: {cleaned_response}")
                raise
        
        # Return result with source info for batch processing
        return {
            "query_dict": query_dict,
            "source_id": source['id'],
            "success": True
        }
        
    except Exception as e:
        logger.error(f"Error generating search query for source {source.get('id', 'unknown')}: {e}")
        # Fallback to basic query
        metadata_raw = source.get('metadata_', '{}')
        if isinstance(metadata_raw, dict):
            source_metadata = metadata_raw
        else:
            try:
                source_metadata = json.loads(metadata_raw)
            except json.JSONDecodeError as json_error:
                logger.error(f"Error parsing source metadata in fallback: {json_error}")
                source_metadata = {}
        fallback_terms = []
        if source.get('description'):
            fallback_terms.append(source['description'])
        if source_metadata.get('publisher_or_court'):
            fallback_terms.append(source_metadata['publisher_or_court'])
        
        fallback_query = ' '.join(fallback_terms)[:150]
        return {
            "query_dict": {"q": fallback_query, "orTerms": ""},
            "source_id": source.get('id', 'unknown'),
            "success": False,
            "error": str(e)
        }


def generate_search_query(ai_client: OpenAiSync, claim: Dict, source: Dict) -> Dict:
    """
    Generate a Google Custom Search query using LLM (single source version)
    
    Args:
        ai_client: OpenAiSync instance
        claim: Dictionary containing claim information
        source: Dictionary containing source information
        
    Returns:
        Dictionary containing search query parameters (q, orTerms)
    """
    result = generate_search_query_batch(ai_client, claim, source)
    return result["query_dict"]


def perform_google_search(query: Dict, google_api_key: str = None, google_engine_id: str = None, source_type: str = None) -> Dict:
    """
    Perform Google Custom Search API call with two-shot approach:
    1. First try with original query (which may include site:domain)
    2. If no results, try with site restriction removed and more:source_type added
    
    Args:
        query: Dictionary containing search query parameters (q, orTerms, etc.)
        google_api_key: Google Custom Search API key (optional, will use env var if not provided)
        google_engine_id: Google Custom Search Engine ID (optional, will use env var if not provided)
        source_type: Type of source to help with fallback search
        
    Returns:
        Dictionary containing search results and metadata
    """
    try:
        # Get credentials from environment if not provided
        if not google_api_key:
            google_api_key = os.getenv("G_SEARCH_API_KEY")
        if not google_engine_id:
            google_engine_id = os.getenv("G_SEARCH_ENG_ID")
            
        if not google_api_key or not google_engine_id:
            logger.error("Google Custom Search API credentials not found in environment variables")
            return {"items": [], "total_results": 0, "search_time": 0, "all_links": [], "query": query, "or_terms": [], "search_attempt": "failed"}
        
        url = "https://www.googleapis.com/customsearch/v1"
        
        # First attempt: with original query (may include site:domain)
        logger.info("Attempting search with original query")
        
        # Start with base parameters
        params = {
            "key": google_api_key,
            "cx": google_engine_id,
            "num": 5,  # Get top 5 results
        }
        
        # Use original query as-is
        params.update(query)
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        results = response.json()
        items = results.get("items", [])
        total_results = results.get("searchInformation", {}).get("totalResults", "0")
        
        logger.info(f"First attempt results: {len(items)} items, {total_results} total")
        
        # If we got results, return them
        if items and int(total_results) > 0:
            return _process_search_results(results, query, "original_query")
        
        # Second attempt: remove site restriction and add more:source_type
        logger.info("No results with original query, trying broader search with source type hint")
        
        # Start with base parameters
        params = {
            "key": google_api_key,
            "cx": google_engine_id,
            "num": 5,  # Get top 5 results
        }
        
        # Create broader query by removing site restriction and adding source type hint
        broader_query = query.copy()
        original_q = broader_query.get('q', '')
        
        # Remove site:domain using string functions
        import re
        # Remove site:domain patterns
        broader_q = re.sub(r'\s*site:[^\s]+', '', original_q)
        broader_q = broader_q.strip()
        
        # Add source type hint
        if source_type:
            broader_q = f"{broader_q} more:{source_type}"
            logger.info(f"Removed site restriction and added source type hint: more:{source_type}")
        
        broader_query['q'] = broader_q
        
        # Update params with broader query
        params.update(broader_query)
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        results = response.json()
        items = results.get("items", [])
        total_results = results.get("searchInformation", {}).get("totalResults", "0")
        
        logger.info(f"Second attempt results: {len(items)} items, {total_results} total")
        
        return _process_search_results(results, broader_query, "broader_search")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error performing Google search: {e}")
        return {"items": [], "total_results": 0, "search_time": 0, "all_links": [], "query": query, "or_terms": [], "search_attempt": "failed"}
    except Exception as e:
        logger.error(f"Unexpected error in Google search: {e}")
        return {"items": [], "total_results": 0, "search_time": 0, "all_links": [], "query": query, "or_terms": [], "search_attempt": "failed"}


def _process_search_results(results: Dict, query: Dict, search_attempt: str) -> Dict:
    """
    Process and format search results
    
    Args:
        results: Raw results from Google Custom Search API
        query: Original query dictionary
        search_attempt: Type of search attempt made
        
    Returns:
        Formatted search metadata
    """
    items = results.get("items", [])
    
    # Extract search metadata
    search_info = results.get("searchInformation", {})
    total_results = search_info.get("totalResults", "0")
    search_time = search_info.get("searchTime", 0)
    
    # Extract all links from search results
    all_links = []
    for item in items:
        all_links.append(item.get("link", ""))
    
    # Extract orTerms from the query if available
    or_terms = []
    queries_info = results.get("queries", {}).get("request", [])
    if queries_info and len(queries_info) > 0:
        or_terms_str = queries_info[0].get("orTerms", "")
        if or_terms_str:
            # Split by spaces and handle quoted phrases
            import re
            or_terms = re.findall(r'"([^"]*)"|\S+', or_terms_str)
    
    search_metadata = {
        "items": items,  # Keep original items for backward compatibility
        "total_results": int(total_results) if total_results.isdigit() else 0,
        "search_time": search_time,
        "all_links": all_links,
        "query": query,
        "or_terms": or_terms,
        "search_attempt": search_attempt
    }
    
    return search_metadata


def process_source_batch(sources: List[Dict], sql_store: SqlStore, ai_client: OpenAiSync, max_workers: int = 7):
    """
    Process a batch of sources using ThreadPoolExecutor for parallel LLM query generation
    
    Args:
        sources: List of source dictionaries to process
        sql_store: SqlStore instance
        ai_client: OpenAiSync instance
        max_workers: Maximum number of parallel workers for LLM queries
    """
    processed_count = 0
    skipped_count = 0
    
    # Form list of source-claim pairs
    source_claim_pairs = []
    for source in sources:
        if is_source_processed(source):
            logger.info(f"Skipping already processed source: {source['id']}")
            skipped_count += 1
        else:
            claim = get_claim_for_source(sql_store, source['id'])
            if claim:
                source_claim_pairs.append((source, claim))
            else:
                logger.warning(f"No claim found for source {source['id']}, skipping")
                skipped_count += 1
    
    if not source_claim_pairs:
        logger.info(f"All sources already processed or no claims found. Skipped: {skipped_count}")
        return
    
    logger.info(f"Processing {len(source_claim_pairs)} sources with {max_workers} parallel workers")
    
    # Use ThreadPoolExecutor to process all sources in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_source = {}
        for source, claim in source_claim_pairs:
            future = executor.submit(generate_search_query_batch, ai_client, claim, source)
            future_to_source[future] = source['id']
        
        # Process results as they complete
        completed_queries = {}
        for future in as_completed(future_to_source):
            source_id = future_to_source[future]
            try:
                result = future.result()
                if isinstance(result, dict) and 'source_id' in result:
                    completed_queries[result['source_id']] = result
                    logger.info(f"Generated query for source: {result['source_id']}")
                else:
                    logger.warning(f"Unexpected result format for source {source_id}: {type(result)}")
            except Exception as e:
                logger.error(f"Error generating query for source {source_id}: {e}")
        
        # Process each source with its generated query
        for source, claim in source_claim_pairs:
            try:
                source_id = source['id']
                if source_id not in completed_queries:
                    logger.warning(f"No query generated for source {source_id}, skipping")
                    continue
                
                query_result = completed_queries[source_id]
                if not query_result.get('success', False):
                    logger.warning(f"Query generation failed for source {source_id}: {query_result.get('error', 'Unknown error')}")
                    continue
                
                query_dict = query_result['query_dict']
                if not query_dict or 'q' not in query_dict:
                    logger.warning(f"Invalid query generated for source {source_id}")
                    continue
                
                # Parse source metadata to get source type
                metadata_raw = source.get('metadata_', '{}')
                if isinstance(metadata_raw, dict):
                    source_metadata = metadata_raw
                else:
                    try:
                        source_metadata = json.loads(metadata_raw)
                    except json.JSONDecodeError:
                        source_metadata = {}
                
                # Perform Google search with two-shot approach
                source_type = source_metadata.get('source_type', '')
                search_metadata = perform_google_search(query_dict, source_type=source_type)
                
                # Update source if good results found
                if search_metadata["items"]:
                    update_source_with_resolution(sql_store, source, search_metadata, query_dict)
                    processed_count += 1
                else:
                    logger.info(f"No search results found for source {source_id}")
                    processed_count += 1  # Still counts as processed even if no results
                    
            except Exception as e:
                logger.error(f"Error processing source {source['id']}: {e}")
                continue
    
    logger.info(f"Batch processing complete: {processed_count} processed, {skipped_count} skipped")


def update_source_with_resolution(sql_store: SqlStore, source: Dict, search_metadata: Dict, query_dict: Dict):
    """
    Update source in database with resolution results
    
    Args:
        sql_store: SqlStore instance
        source: Original source dictionary
        search_metadata: Dictionary containing Google search results and metadata
        query_dict: The query dictionary that was used
    """
    try:
        # Take the best (first) result
        search_results = search_metadata["items"]
        best_result = search_results[0]
        resolved_url = best_result['link']
        
        # Check if another source already exists with this URL
        existing_source = check_existing_source_by_url(sql_store, resolved_url)
        
        if existing_source and existing_source['id'] != source['id']:
            # Another source already exists with this URL - merge them
            logger.info(f"Found existing source {existing_source['id']} with same URL {resolved_url}")
            merge_sources(sql_store, source, existing_source, search_metadata, query_dict)
        else:
            # No existing source with this URL - update normally
            update_source_directly(sql_store, source, search_metadata, query_dict)
        
    except Exception as e:
        logger.error(f"Error updating source {source['id']} with resolution: {e}")


def check_existing_source_by_url(sql_store: SqlStore, url: str) -> Optional[Dict]:
    """
    Check if a source already exists with the given URL
    
    Args:
        sql_store: SqlStore instance
        url: URL to check for
        
    Returns:
        Existing source dictionary if found, None otherwise
    """
    try:
        # Use SQL API method to check for existing source
        existing_source = sql_store.get_source_by_url(url)
        return existing_source
                
    except Exception as e:
        logger.error(f"Error checking for existing source with URL {url}: {e}")
        return None


def merge_sources(sql_store: SqlStore, source_to_merge: Dict, target_source: Dict, 
                 search_metadata: Dict, query_dict: Dict):
    """
    Merge a source into an existing source by transferring edges and updating metadata
    
    Args:
        sql_store: SqlStore instance
        source_to_merge: Source that will be merged (and eventually deleted)
        target_source: Existing source that will receive the edges
        search_metadata: Search metadata for logging purposes
        query_dict: Query dictionary used for logging purposes
    """
    try:
        logger.info(f"Merging source {source_to_merge['id']} into existing source {target_source['id']}")
        
        # Transfer all edges from source_to_merge to target_source
        transferred_edges = transfer_source_edges(sql_store, source_to_merge['id'], target_source['id'])
        
        # Update target source metadata to include information from merged source
        update_target_source_metadata(sql_store, target_source, source_to_merge, search_metadata, query_dict)
        
        # Delete the merged source
        delete_merged_source(sql_store, source_to_merge['id'])
        
        logger.info(f"Successfully merged source {source_to_merge['id']} into {target_source['id']} "
                   f"(transferred {transferred_edges} edges)")
        
    except Exception as e:
        logger.error(f"Error merging sources {source_to_merge['id']} into {target_source['id']}: {e}")


def transfer_source_edges(sql_store: SqlStore, source_id: str, target_source_id: str) -> int:
    """
    Transfer all edges connected to a source to another source
    
    Args:
        sql_store: SqlStore instance
        source_id: ID of source whose edges will be transferred
        target_source_id: ID of source that will receive the edges
        
    Returns:
        Number of edges transferred
    """
    try:
        from sqlalchemy import text
        
        # First, get all edges where this source is the destination
        query = text("""
        SELECT * FROM edges 
        WHERE dest_id = :source_id AND dest_type = 'source'
        """)
        
        with sql_store.engine.connect() as connection:
            result = connection.execute(query, {"source_id": source_id})
            edges_to_transfer = result.fetchall()
            
            transferred_count = 0
            
            for edge_row in edges_to_transfer:
                edge_data = dict(zip(result.keys(), edge_row))
                
                # Create new edge pointing to target source
                edge_metadata_raw = edge_data.get('metadata_', '{}')
                if isinstance(edge_metadata_raw, dict):
                    edge_metadata = edge_metadata_raw
                elif edge_metadata_raw:
                    try:
                        edge_metadata = json.loads(edge_metadata_raw)
                    except json.JSONDecodeError:
                        edge_metadata = {}
                else:
                    edge_metadata = {}
                
                new_edge_id = sql_store.create_edge(
                    src_type=edge_data['src_type'],
                    src_id=edge_data['src_id'],
                    dest_type='source',
                    dest_id=target_source_id,
                    relationship_type=edge_data['relationship_type'],
                    metadata=edge_metadata
                )
                
                if new_edge_id:
                    # Delete the old edge
                    delete_query = text("DELETE FROM edges WHERE id = :edge_id")
                    connection.execute(delete_query, {"edge_id": edge_data['id']})
                    transferred_count += 1
            
            connection.commit()
            return transferred_count
            
    except Exception as e:
        logger.error(f"Error transferring edges from {source_id} to {target_source_id}: {e}")
        return 0


def update_target_source_metadata(sql_store: SqlStore, target_source: Dict, merged_source: Dict,
                                search_metadata: Dict, query_dict: Dict):
    """
    Update target source metadata to include information from the merged source
    
    Args:
        sql_store: SqlStore instance
        target_source: Source that will be updated
        merged_source: Source that was merged (for metadata extraction)
        search_metadata: Search metadata for logging
        query_dict: Query dictionary used for logging
    """
    try:
        # Parse existing metadata
        target_metadata_raw = target_source.get('metadata_', '{}')
        if isinstance(target_metadata_raw, dict):
            target_metadata = target_metadata_raw
        else:
            try:
                target_metadata = json.loads(target_metadata_raw)
            except json.JSONDecodeError:
                target_metadata = {}
        
        merged_metadata_raw = merged_source.get('metadata_', '{}')
        if isinstance(merged_metadata_raw, dict):
            merged_metadata = merged_metadata_raw
        else:
            try:
                merged_metadata = json.loads(merged_metadata_raw)
            except json.JSONDecodeError:
                merged_metadata = {}
        
        # Merge metadata arrays (like search_query)
        if 'search_query' in merged_metadata and merged_metadata['search_query']:
            if 'search_query' not in target_metadata:
                target_metadata['search_query'] = []
            target_metadata['search_query'].extend(merged_metadata['search_query'])
            # Remove duplicates
            target_metadata['search_query'] = list(set(target_metadata['search_query']))
        
        # Add merge information
        if 'merged_sources' not in target_metadata:
            target_metadata['merged_sources'] = []
        
        target_metadata['merged_sources'].append({
            'source_id': merged_source['id'],
            'original_description': merged_source.get('description', ''),
            'original_url': merged_source.get('link', ''),  # Store original URL for audit
            'merge_timestamp': time.time(),
            'search_results': {
                "total_results": search_metadata['total_results'],
                "links": search_metadata['all_links'],
                "query": {
                    "query": query_dict.get('q', ''),
                    "orTerms": query_dict.get('orTerms', '').split() if query_dict.get('orTerms') else []
                }
            }
        })
        
        # Update the target source
        sql_store.update_data('sources', target_source['id'], {
            'metadata_': json.dumps(target_metadata)
        })
        
        logger.info(f"Updated metadata for target source {target_source['id']}")
        
    except Exception as e:
        logger.error(f"Error updating target source metadata: {e}")


def delete_merged_source(sql_store: SqlStore, source_id: str):
    """
    Delete a source that has been merged into another source
    
    Args:
        sql_store: SqlStore instance
        source_id: ID of source to delete
    """
    try:
        # Delete the source
        deleted_count = sql_store.delete_data('sources', source_id)
        logger.info(f"Deleted merged source {source_id} ({deleted_count} rows affected)")
        
    except Exception as e:
        logger.error(f"Error deleting merged source {source_id}: {e}")


def extract_creation_date(search_result: Dict) -> Optional[str]:
    """
    Extract creation date from a Google search result
    
    Args:
        search_result: Google search result item
        
    Returns:
        Creation date string if found, None otherwise
    """
    try:
        # Check for creation date in pagemap metadata
        pagemap = search_result.get('pagemap', {})
        metatags = pagemap.get('metatags', [])
        
        if metatags and len(metatags) > 0:
            metatag = metatags[0]
            # Try different possible creation date fields
            creation_date = (
                metatag.get('creationdate') or 
                metatag.get('article:published_time') or
                metatag.get('og:updated_time') or
                metatag.get('date') or
                metatag.get('pubdate')
            )
            if creation_date:
                return creation_date
        
        return None
        
    except Exception as e:
        logger.debug(f"Error extracting creation date: {e}")
        return None


def update_source_directly(sql_store: SqlStore, source: Dict, search_metadata: Dict, query_dict: Dict):
    """
    Update source directly with resolution results (no merging needed)
    
    Args:
        sql_store: SqlStore instance
        source: Source to update
        search_metadata: Search metadata containing results and additional info
        query_dict: Query dictionary used
    """
    try:
        # Take the best (first) result
        search_results = search_metadata["items"]
        best_result = search_results[0]
        
        # Extract creation date from the best result
        creation_date = extract_creation_date(best_result)
        
        # Parse existing metadata
        metadata_raw = source.get('metadata_', '{}')
        if isinstance(metadata_raw, dict):
            metadata = metadata_raw
        else:
            try:
                metadata = json.loads(metadata_raw)
            except json.JSONDecodeError:
                metadata = {}
        
        # Update metadata with resolution info
        metadata['match_status'] = 'resolved'
        metadata['original_url'] = source.get('link', '')  # Store the original URL for audit
        metadata['resolved_title'] = best_result['title']
        metadata['resolution_timestamp'] = time.time()
        
        # Add structured search metadata
        metadata['search_results'] = {
            "total_results": search_metadata['total_results'],
            "links": search_metadata['all_links'],
            "query": {
                "query": query_dict.get('q', ''),
                "orTerms": query_dict.get('orTerms', '').split() if query_dict.get('orTerms') else []
            }
        }
        
        # Add creation date if found
        if creation_date:
            metadata['create_date'] = creation_date
        
        # Update the source in database
        update_result = sql_store.update_data('sources', source['id'], {
            'link': best_result['link'],  # Update the main link field
            'metadata_': json.dumps(metadata)
        })
        
        logger.info(f"Successfully resolved source {source['id']} to: {best_result['link']} "
                   f"(total results: {search_metadata['total_results']})")
        
    except Exception as e:
        logger.error(f"Error updating source {source['id']} directly: {e}")


def main():
    """
    Main function to run source resolution when called directly from terminal.
    Sets up logging and runs the resolution process.
    """
    # Set up logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),  # Console output
            logging.FileHandler(PROJ_ROOT / "logs" / f"resolve_sources_{time.strftime('%Y%m%d_%H%M%S')}.log")
        ]
    )
    
    logger.info("Starting standalone source resolution process")
    
    try:
        resolve_unresolved_sources()
        logger.info("Source resolution process completed successfully")
    except Exception as e:
        logger.error(f"Source resolution process failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
