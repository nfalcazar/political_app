"""
Claim Relationship Classifier Module

This module provides functionality to:
1. Find similar claims using vector similarity search
2. Classify relationships between claims using LLM
3. Store relationships in the edge table with confidence scores
4. Handle both canonical claims and regular claims

Can be used as a single function call for BackgroundScheduler integration.
"""

import logging
import json
import ast
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import time
from pathlib import Path
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor, as_completed

from database.sql_api import SqlStore
from database.vector_api import VectorStore
from util.ai_ext_calls import OpenAiSync
from timescale_vector.client import uuid_from_time

logger = logging.getLogger(__name__)

class ClaimRelationshipClassifier:
    """
    Classifies relationships between claims using vector similarity and LLM analysis.
    Uses @classmethod approach for consistency with existing codebase.
    """
    
    # Class-level configuration
    SIMILARITY_THRESHOLD = 0.75
    MAX_SIMILAR_CLAIMS = 10
    BATCH_SIZE = 5
    LLM_PROVIDER = "openai"
    LOG_PROGRESS_INTERVAL = 25
    RATE_LIMIT_DELAY = 0.1
    MAX_PARALLEL_WORKERS = 10  # Maximum number of parallel LLM workers
    BATCH_DELAY_SECONDS = 5  # Delay between batches to avoid rate limiting
    
    
    
    @classmethod
    def _get_all_canon_claims(cls, sql_store: SqlStore) -> List[Dict[str, Any]]:
        """Get all canonical claims from the database."""
        try:
            with sql_store.engine.connect() as connection:
                query = text("SELECT id, contents, metadata, embedding FROM canon_claims")
                result = connection.execute(query)
                claims = []
                for row in result:
                    claims.append({
                        'id': str(row.id),  # Convert UUID to string
                        'content': row.contents,  # Using 'contents' column as 'content'
                        'metadata': row.metadata if row.metadata else {},  # metadata is already a dict
                        'embedding': cls._parse_embedding(row.embedding)  # Parse embedding string to list
                    })
                return claims
        except Exception as e:
            logger.error(f"Error getting canonical claims: {e}")
            return []

    @classmethod
    def _get_all_claims(cls, sql_store: SqlStore) -> List[Dict[str, Any]]:
        """Get all claims from the database."""
        try:
            with sql_store.engine.connect() as connection:
                query = text("SELECT id, contents, metadata, embedding FROM claims")
                result = connection.execute(query)
                claims = []
                for row in result:
                    claims.append({
                        'id': str(row.id),  # Convert UUID to string
                        'content': row.contents,  # Using 'contents' column as 'content'
                        'metadata': row.metadata if row.metadata else {},  # metadata is already a dict
                        'embedding': cls._parse_embedding(row.embedding)  # Parse embedding string to list
                    })
                return claims
        except Exception as e:
            logger.error(f"Error getting claims: {e}")
            return []


    @classmethod
    def _parse_embedding(cls, embedding_data) -> List[float]:
        """Parse embedding data from database format to list of floats."""
        try:
            if embedding_data is None:
                return []
            
            # If it's already a list, return it
            if isinstance(embedding_data, list):
                return embedding_data
            
            # If it's a string, use ast.literal_eval for safe parsing
            if isinstance(embedding_data, str):
                return ast.literal_eval(embedding_data)
            
            # If it's a numpy array or similar, convert to list
            return list(embedding_data)
            
        except Exception as e:
            logger.error(f"Error parsing embedding: {e}")
            return []

    @classmethod
    def _is_claim_processed(cls, sql_store: SqlStore, claim_id: str, claim_type: str) -> bool:
        """Check if a claim has already been processed for relationships."""
        try:
            # Check if the claim has any relationships
            existing_relationships = sql_store.check_claim_relationship(claim_id, claim_type)
            return len(existing_relationships) > 0
        except Exception as e:
            logger.error(f"Error checking if claim processed: {e}")
            return False

    @classmethod
    def _should_process_claim_pair(cls, sql_store: SqlStore, src_id: str, dest_id: str, 
                                  claim_type: str, seen_relationships: set = None) -> bool:
        """
        Check if a claim pair should be processed by the LLM.
        Returns True if the pair should be processed, False if relationship already exists.
        
        Args:
            sql_store: Database store
            src_id: Source claim ID
            dest_id: Destination claim ID
            claim_type: Type of claims being processed
            seen_relationships: Set of already seen relationships within current batch (optional)
        """
        # Check database for existing relationships
        existing_types = sql_store.check_claim_relationship(src_id, claim_type, other_claim_id=dest_id)
        
        # If any relationship types exist in database, skip processing
        if existing_types:
            logger.debug(f"Database relationship exists between {src_id} and {dest_id}: {existing_types}")
            return False
        
        # Check for intra-batch duplicates if seen_relationships is provided
        if seen_relationships is not None:
            # Create bidirectional keys to check for duplicates within this batch
            relationship_key_forward = (src_id, dest_id)
            relationship_key_reverse = (dest_id, src_id)
            
            if relationship_key_forward in seen_relationships or relationship_key_reverse in seen_relationships:
                logger.debug(f"Intra-batch duplicate detected between {src_id} and {dest_id}")
                return False
        
        return True

    
    @classmethod
    def _find_similar_canon_claims(cls, vector_store: VectorStore, claim: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find similar canonical claims using vector search."""
        try:
            # Use existing embedding from the claim
            embedding = claim['embedding']
            
            # Search for similar claims using class configuration
            similar_results = vector_store.search_by_embed(
                embedding,
                limit=cls.MAX_SIMILAR_CLAIMS + 1,  # +1 to exclude self
                return_dataframe=True
            )
            
            # Filter results using class configuration
            similar_claims = []
            for _, row in similar_results.iterrows():
                # Skip if it's the same claim
                if row['id'] == claim['id']:
                    continue
                
                # Convert distance to similarity (1 - distance)
                distance = row['distance']
                similarity = 1 - distance
                
                # Check similarity threshold using class configuration
                if similarity >= cls.SIMILARITY_THRESHOLD:
                    similar_claims.append({
                        'id': row['id'],
                        'content': row['contents'],  # canon_claims table uses 'contents'
                        'similarity': similarity,
                        'metadata': row.get('metadata', {})  # canon_claims table uses 'metadata'
                    })
            
            # Log when similar claims are found
            if similar_claims:
                similarity_scores = [f"{claim['similarity']:.3f}" for claim in similar_claims]
                logger.info(f"Found {len(similar_claims)} similar canonical claims for claim {claim['id']} with similarity scores: {similarity_scores}")
                logger.debug(f"Similar canonical claims for {claim['id']}: {[claim['id'] for claim in similar_claims]}")
            else:
                logger.debug(f"No similar canonical claims found for claim {claim['id']} (threshold: {cls.SIMILARITY_THRESHOLD})")
            
            return similar_claims[:cls.MAX_SIMILAR_CLAIMS]
        
        except Exception as e:
            logger.error(f"Error finding similar canonical claims: {e}")
            return []

    @classmethod
    def _find_similar_claims(cls, vector_store: VectorStore, claim: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find similar claims using vector search."""
        try:
            # Use existing embedding from the claim
            embedding = claim['embedding']
            
            # Search for similar claims using class configuration
            similar_results = vector_store.search_by_embed(
                embedding,
                limit=cls.MAX_SIMILAR_CLAIMS + 1,  # +1 to exclude self
                return_dataframe=True
            )
            
            # Filter results using class configuration
            similar_claims = []
            for _, row in similar_results.iterrows():
                # Skip if it's the same claim
                if row['id'] == claim['id']:
                    continue
                
                # Convert distance to similarity (1 - distance)
                distance = row['distance']
                similarity = 1 - distance
                
                # Check similarity threshold using class configuration
                if similarity >= cls.SIMILARITY_THRESHOLD:
                    similar_claims.append({
                        'id': row['id'],
                        'content': row['contents'],  # claims table uses 'contents'
                        'similarity': similarity,
                        'metadata': row.get('metadata', {})  # claims table uses 'metadata'
                    })
            
            # Log when similar claims are found
            if similar_claims:
                similarity_scores = [f"{claim['similarity']:.3f}" for claim in similar_claims]
                logger.info(f"Found {len(similar_claims)} similar claims for claim {claim['id']} with similarity scores: {similarity_scores}")
                logger.debug(f"Similar claims for {claim['id']}: {[claim['id'] for claim in similar_claims]}")
            else:
                logger.debug(f"No similar claims found for claim {claim['id']} (threshold: {cls.SIMILARITY_THRESHOLD})")
            
            return similar_claims[:cls.MAX_SIMILAR_CLAIMS]
        
        except Exception as e:
            logger.error(f"Error finding similar claims: {e}")
            return []
    
    @classmethod
    def _classify_relationships_batch(cls, ai_client: OpenAiSync, base_claim: Dict[str, Any], 
                                    similar_claims: List[Dict[str, Any]], claim_type: str,
                                    system_prompt: str) -> List[Dict[str, Any]]:
        """Classify relationships between a base claim and similar claims using parallel batch processing."""
        relationships = []
        
        # Process in batches using class configuration
        for i in range(0, len(similar_claims), cls.BATCH_SIZE):
            batch = similar_claims[i:i + cls.BATCH_SIZE]
            
            try:
                batch_relationships = cls._classify_claim_batch_parallel(ai_client, base_claim, batch, claim_type, system_prompt)
                relationships.extend(batch_relationships)
                
                # Small delay to avoid rate limiting using class configuration
                time.sleep(cls.RATE_LIMIT_DELAY)
            
            except Exception as e:
                logger.error(f"Error classifying batch {i//cls.BATCH_SIZE + 1}: {e}")
                continue
        
        return relationships

    @classmethod
    def _classify_multiple_base_claims_parallel(cls, ai_client: OpenAiSync, base_claims_with_similar: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]], 
                                               claim_type: str, system_prompt: str) -> List[Dict[str, Any]]:
        """Classify relationships for multiple base claims with their similar claims using parallel processing with rate limiting."""
        relationships = []
        
        # Process in batches to avoid rate limiting
        batch_size = cls.MAX_PARALLEL_WORKERS
        total_batches = (len(base_claims_with_similar) + batch_size - 1) // batch_size
        
        logger.info(f"Processing {len(base_claims_with_similar)} base claims in {total_batches} batches of {batch_size}")
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(base_claims_with_similar))
            batch_items = base_claims_with_similar[start_idx:end_idx]
            
            logger.info(f"Processing batch {batch_num + 1}/{total_batches} with {len(batch_items)} items")
            
            # Use ThreadPoolExecutor for parallel LLM processing within this batch
            max_workers = min(cls.MAX_PARALLEL_WORKERS, len(batch_items))
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks for this batch
                future_to_base_claim = {}
                for base_claim, similar_claims in batch_items:
                    future = executor.submit(
                        cls._classify_base_claim_with_similar_claims, 
                        ai_client, 
                        base_claim, 
                        similar_claims, 
                        claim_type, 
                        system_prompt
                    )
                    future_to_base_claim[future] = base_claim['id']
                
                # Process results as they complete
                for future in as_completed(future_to_base_claim):
                    base_claim_id = future_to_base_claim[future]
                    try:
                        result = future.result()
                        if result:
                            relationships.extend(result)
                            logger.debug(f"Classified relationships for base claim {base_claim_id}")
                        else:
                            logger.warning(f"No relationships classified for base claim {base_claim_id}")
                    except Exception as e:
                        logger.error(f"Error classifying relationships for base claim {base_claim_id}: {e}")
            
            # Add delay between batches (except for the last batch)
            if batch_num < total_batches - 1:
                logger.info(f"Waiting {cls.BATCH_DELAY_SECONDS} seconds before next batch...")
                time.sleep(cls.BATCH_DELAY_SECONDS)
        
        return relationships

    @classmethod
    def _classify_claim_batch(cls, ai_client: OpenAiSync, base_claim: Dict[str, Any], 
                             similar_claims: List[Dict[str, Any]], claim_type: str,
                             system_prompt: str) -> List[Dict[str, Any]]:
        """Classify relationships for a batch of claim pairs."""
        
        # Update user prompt to include neutral relationships
        user_prompt = f"""
        Analyze the relationships between these {len(similar_claims)} pairs of claims.
        
        {''.join([f"PAIR {i+1}:\nCLAIM 1: {base_claim['content']}\nCLAIM 2: {similar_claims[i]['content']}\n" for i in range(len(similar_claims))])}
        
        For each pair, determine:
        1. The relationship type: supports, opposes, or neutral
        2. A confidence score from 0.1 to 1.0
        3. Brief reasoning for the classification
        
        Follow the exact JSON format specified in the system prompt.
        """
        
        # Prepare batch input for LLM
        batch_input = []
        for i, similar_claim in enumerate(similar_claims):
            batch_input.append(f"""
            PAIR {i+1}:
            CLAIM 1: {base_claim['content']}
            CLAIM 2: {similar_claim['content']}
            """)
        
        user_prompt = f"""
        Analyze the relationships between these {len(similar_claims)} pairs of claims.
        
        {''.join(batch_input)}
        
        For each pair, determine:
        1. The relationship type: supports, opposes, or uncertain
        2. A confidence score from 0.1 to 1.0
        3. Brief reasoning for the classification
        
        Follow the exact JSON format specified in the system prompt.
        """
        
        try:
            response = ai_client.query(user_prompt, system_prompt)
            batch_results = json.loads(response)
            
            # Convert batch results to relationship objects
            relationships = []
            for i, result in enumerate(batch_results):
                if i < len(similar_claims):
                    relationship = {
                        'src_type': claim_type,
                        'src_id': base_claim['id'],
                        'dest_type': claim_type,
                        'dest_id': similar_claims[i]['id'],
                        'relationship_type': result['relationship'].lower(),
                        'confidence': result['confidence'],
                        'reasoning': result['reasoning'],
                        'similarity_score': similar_claims[i]['similarity']
                    }
                    relationships.append(relationship)
            
            return relationships
        
        except Exception as e:
            logger.error(f"Error in LLM classification: {e}")
            return []

    @classmethod
    def _classify_claim_batch_parallel(cls, ai_client: OpenAiSync, base_claim: Dict[str, Any], 
                                      similar_claims: List[Dict[str, Any]], claim_type: str,
                                      system_prompt: str) -> List[Dict[str, Any]]:
        """Classify relationships for a base claim with all its similar claims using parallel processing."""
        
        # Use ThreadPoolExecutor for parallel LLM processing
        # Each base claim with its similar claims is treated as a single batch item
        max_workers = cls.MAX_PARALLEL_WORKERS
        relationships = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit the single task for this base claim with all its similar claims
            future = executor.submit(
                cls._classify_base_claim_with_similar_claims, 
                ai_client, 
                base_claim, 
                similar_claims, 
                claim_type, 
                system_prompt
            )
            
            # Process the result
            try:
                result = future.result()
                if result:
                    relationships.extend(result)
                    logger.debug(f"Classified relationships for base claim {base_claim['id']} with {len(similar_claims)} similar claims")
                else:
                    logger.warning(f"No relationships classified for base claim {base_claim['id']}")
            except Exception as e:
                logger.error(f"Error classifying relationships for base claim {base_claim['id']}: {e}")
        
        return relationships

    @classmethod
    def _classify_base_claim_with_similar_claims(cls, ai_client: OpenAiSync, base_claim: Dict[str, Any], 
                                                similar_claims: List[Dict[str, Any]], claim_type: str,
                                                system_prompt: str) -> Optional[List[Dict[str, Any]]]:
        """Classify relationships for a base claim with all its similar claims in a single LLM call."""
        
        # Prepare batch input for LLM - all similar claims with the base claim
        batch_input = []
        for i, similar_claim in enumerate(similar_claims):
            batch_input.append(f"""
            PAIR {i+1}:
            CLAIM 1: {base_claim['content']}
            CLAIM 2: {similar_claim['content']}
            """)
        
        user_prompt = f"""
        Analyze the relationships between these {len(similar_claims)} pairs of claims.
        
        {''.join(batch_input)}
        
        For each pair, determine:
        1. The relationship type: supports, opposes, or neutral
        2. A confidence score from 0.1 to 1.0
        3. Brief reasoning for the classification
        
        Follow the exact JSON format specified in the system prompt.
        """
        
        try:
            response = ai_client.query(user_prompt, system_prompt)
            batch_results = json.loads(response)
            
            # Convert batch results to relationship objects
            relationships = []
            for i, result in enumerate(batch_results):
                if i < len(similar_claims):
                    relationship = {
                        'src_type': claim_type,
                        'src_id': base_claim['id'],
                        'dest_type': claim_type,
                        'dest_id': similar_claims[i]['id'],
                        'relationship_type': result['relationship'].lower(),
                        'confidence': result['confidence'],
                        'reasoning': result['reasoning'],
                        'similarity_score': similar_claims[i]['similarity']
                    }
                    relationships.append(relationship)
            
            return relationships
            
        except Exception as e:
            logger.error(f"Error in batch classification for base claim {base_claim['id']}: {e}")
            return None

    @classmethod
    def _filter_and_store_relationships(cls, sql_store: SqlStore, relationships: List[Dict[str, Any]]) -> int:
        """Filter out neutral relationships and store the rest in the edge table. Duplicate checking is done during batch formation."""
        created_count = 0
        neutral_count = 0
        
        for relationship in relationships:
            try:
                # Skip neutral relationships - they don't create edges
                if relationship['relationship_type'] == 'neutral':
                    neutral_count += 1
                    logger.debug(f"Skipping neutral relationship between {relationship['src_id']} and {relationship['dest_id']}")
                    continue
                
                # Prepare metadata
                metadata = {
                    'confidence': relationship['confidence'],
                    'reasoning': relationship['reasoning'],
                    'similarity_score': relationship['similarity_score'],
                    'classified_at': datetime.now().isoformat(),
                    'classifier_version': '1.0'
                }
                
                # Create edge
                edge_id = sql_store.create_edge(
                    src_type=relationship['src_type'],
                    src_id=relationship['src_id'],
                    dest_type=relationship['dest_type'],
                    dest_id=relationship['dest_id'],
                    relationship_type=relationship['relationship_type'],
                    metadata=metadata
                )
                
                if edge_id:
                    created_count += 1
            
            except Exception as e:
                logger.error(f"Error storing relationship: {e}")
                continue
        
        if neutral_count > 0:
            logger.info(f"Filtered out {neutral_count} neutral relationships")
        
        return created_count

    @classmethod
    def _store_relationships(cls, sql_store: SqlStore, relationships: List[Dict[str, Any]]) -> int:
        """Store relationships in the edge table."""
        return cls._filter_and_store_relationships(sql_store, relationships)


    @classmethod
    def classify_claim_relationships(cls, table_type: str = "both", force_reprocess: bool = False) -> Dict[str, Any]:
        """
        Classify relationships between claims using vector similarity and LLM analysis.
        
        Args:
            table_type: "canon_claims", "claims", or "both"
            force_reprocess: If True, reprocess existing relationships
            
        Returns:
            Dictionary with processing statistics
        """
        logger.info(f"Starting claim relationship classification for {table_type}")
        start_time = time.time()
        
        stats = {
            'canon_claims_processed': 0,
            'claims_processed': 0,
            'relationships_created': 0,
            'errors': 0,
            'processing_time': 0
        }
        
        try:
            # Initialize components using class configuration
            ai_client = OpenAiSync(provider=cls.LLM_PROVIDER)
            sql_store = SqlStore()
            canon_vector_store = VectorStore("canon_claims")
            claims_vector_store = VectorStore("claims")
            
            # Load system prompt
            classification_system_prompt = cls._load_system_prompt()
            
            if table_type in ["canon_claims", "both"]:
                canon_stats = cls._process_canon_claims(
                    force_reprocess, ai_client, sql_store, canon_vector_store, 
                    classification_system_prompt
                )
                stats['canon_claims_processed'] = canon_stats['processed']
                stats['relationships_created'] += canon_stats['relationships_created']
                stats['errors'] += canon_stats['errors']
            
            if table_type in ["claims", "both"]:
                claims_stats = cls._process_regular_claims(
                    force_reprocess, ai_client, sql_store, claims_vector_store,
                    classification_system_prompt
                )
                stats['claims_processed'] = claims_stats['processed']
                stats['relationships_created'] += claims_stats['relationships_created']
                stats['errors'] += claims_stats['errors']
            
            stats['processing_time'] = time.time() - start_time
            logger.info(f"Relationship classification completed: {stats}")
            
        except Exception as e:
            logger.error(f"Error in claim relationship classification: {e}")
            stats['errors'] += 1
        
        return stats


    @classmethod
    def _load_system_prompt(cls) -> str:
        """Load the system prompt from the prompts directory."""
        try:
            prompt_file = Path(__file__).parent.parent / "prompts" / "relationship_classification_sys.txt"
            with open(prompt_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")
            # Fallback to a basic prompt if file loading fails
            return """
            You are an expert fact-checker. Analyze claim pairs and classify relationships as:
            - "supports": Claims that validate or strengthen each other
            - "opposes": Claims that contradict or weaken each other
            - "uncertain": Unclear or ambiguous relationships
            
            Return JSON array with: pair_id, relationship, confidence (0.1-1.0), reasoning.
            """


    @classmethod
    def _process_canon_claims(cls, force_reprocess: bool, ai_client: OpenAiSync, sql_store: SqlStore, 
                             vector_store: VectorStore, system_prompt: str) -> Dict[str, int]:
        """Process relationships between canonical claims using parallel processing."""
        logger.info("Processing canonical claims relationships")
        
        stats = {'processed': 0, 'relationships_created': 0, 'errors': 0, 'skipped_pairs': 0, 'total_pairs': 0}
        
        try:
            # Get all canonical claims
            canon_claims = cls._get_all_canon_claims(sql_store)
            logger.info(f"Found {len(canon_claims)} canonical claims to process")
            
            # Collect all base claims with their similar claims for parallel processing
            base_claims_with_similar = []
            
            # Track seen relationships within this batch to prevent intra-batch duplicates
            seen_relationships = set()
            
            for i, claim in enumerate(canon_claims):
                try:
                    # Skip if already processed (unless force_reprocess)
                    if not force_reprocess and cls._is_claim_processed(sql_store, claim['id'], 'canonical_claim'):
                        logger.info(f"Detected existing relationship for claim id: {claim['id']}")
                        stats['processed'] += 1
                        continue
                    
                    # Find similar claims using class configuration
                    similar_claims = cls._find_similar_canon_claims(vector_store, claim)
                    
                    # Filter out claims that already have relationships or shouldn't be processed
                    filtered_similar_claims = []
                    skipped_count = 0
                    total_pairs = len(similar_claims)
                    
                    for similar_claim in similar_claims:
                        if cls._should_process_claim_pair(sql_store, claim['id'], similar_claim['id'], 'canonical_claim', seen_relationships):
                            filtered_similar_claims.append(similar_claim)
                            # Add to seen relationships to prevent future duplicates
                            seen_relationships.add((claim['id'], similar_claim['id']))
                            seen_relationships.add((similar_claim['id'], claim['id']))
                        else:
                            skipped_count += 1
                    
                    stats['total_pairs'] += total_pairs
                    stats['skipped_pairs'] += skipped_count
                    
                    if skipped_count > 0:
                        logger.debug(f"Skipped {skipped_count}/{total_pairs} similar claims for canonical claim {claim['id']} (already processed or duplicate)")
                    
                    if filtered_similar_claims:
                        base_claims_with_similar.append((claim, filtered_similar_claims))
                    
                    stats['processed'] += 1
                    
                    # Log progress using class configuration
                    if (i + 1) % cls.LOG_PROGRESS_INTERVAL == 0:
                        logger.info(f"Collected {i + 1}/{len(canon_claims)} canonical claims for processing")
                
                except Exception as e:
                    logger.error(f"Error processing canonical claim {claim['id']}: {e}")
                    stats['errors'] += 1
                    continue
            
            # Process all collected base claims with their similar claims in parallel
            if base_claims_with_similar:
                logger.info(f"Processing {len(base_claims_with_similar)} canonical claims with similar claims in parallel")
                all_relationships = cls._classify_multiple_base_claims_parallel(
                    ai_client, base_claims_with_similar, 'canonical_claim', system_prompt
                )
                
                # Store all relationships
                created_count = cls._store_relationships(sql_store, all_relationships)
                stats['relationships_created'] += created_count
                
                # Log cost savings statistics
                if stats['total_pairs'] > 0:
                    savings_percentage = (stats['skipped_pairs'] / stats['total_pairs']) * 100
                    logger.info(f"Canonical claims processing complete:")
                    logger.info(f"  - Total pairs considered: {stats['total_pairs']}")
                    logger.info(f"  - Pairs skipped (cost savings): {stats['skipped_pairs']}")
                    logger.info(f"  - Pairs processed: {stats['total_pairs'] - stats['skipped_pairs']}")
                    logger.info(f"  - Cost savings: {savings_percentage:.1f}%")
                    logger.info(f"  - Relationships created: {created_count}")
                else:
                    logger.info(f"Created {created_count} relationships for canonical claims")
        
        except Exception as e:
            logger.error(f"Error in canonical claims processing: {e}")
            stats['errors'] += 1
        
        return stats


    @classmethod
    def _process_regular_claims(cls, force_reprocess: bool, ai_client: OpenAiSync, sql_store: SqlStore,
                               vector_store: VectorStore, system_prompt: str) -> Dict[str, int]:
        """Process relationships between regular claims using parallel processing."""
        logger.info("Processing regular claims relationships")
        
        stats = {'processed': 0, 'relationships_created': 0, 'errors': 0, 'skipped_pairs': 0, 'total_pairs': 0}
        
        try:
            # Get all claims
            claims = cls._get_all_claims(sql_store)
            logger.info(f"Found {len(claims)} claims to process")
            
            # Collect all base claims with their similar claims for parallel processing
            base_claims_with_similar = []
            
            # Track seen relationships within this batch to prevent intra-batch duplicates
            seen_relationships = set()
            
            for i, claim in enumerate(claims):
                try:
                    # Skip if already processed (unless force_reprocess)
                    if not force_reprocess and cls._is_claim_processed(sql_store, claim['id'], 'claim'):
                        stats['processed'] += 1
                        continue
                    
                    # Find similar claims using class configuration
                    similar_claims = cls._find_similar_claims(vector_store, claim)
                    
                    # Filter out claims that already have relationships or shouldn't be processed
                    filtered_similar_claims = []
                    skipped_count = 0
                    total_pairs = len(similar_claims)
                    
                    for similar_claim in similar_claims:
                        if cls._should_process_claim_pair(sql_store, claim['id'], similar_claim['id'], 'claim', seen_relationships):
                            filtered_similar_claims.append(similar_claim)
                            # Add to seen relationships to prevent future duplicates
                            seen_relationships.add((claim['id'], similar_claim['id']))
                            seen_relationships.add((similar_claim['id'], claim['id']))
                        else:
                            skipped_count += 1
                    
                    stats['total_pairs'] += total_pairs
                    stats['skipped_pairs'] += skipped_count
                    
                    if skipped_count > 0:
                        logger.debug(f"Skipped {skipped_count}/{total_pairs} similar claims for claim {claim['id']} (already processed or duplicate)")
                    
                    if filtered_similar_claims:
                        base_claims_with_similar.append((claim, filtered_similar_claims))
                    
                    stats['processed'] += 1
                    
                    # Log progress using class configuration
                    if (i + 1) % cls.LOG_PROGRESS_INTERVAL == 0:
                        logger.info(f"Collected {i + 1}/{len(claims)} claims for processing")
                
                except Exception as e:
                    logger.error(f"Error processing claim {claim['id']}: {e}")
                    stats['errors'] += 1
                    continue
            
            # Process all collected base claims with their similar claims in parallel
            if base_claims_with_similar:
                logger.info(f"Processing {len(base_claims_with_similar)} claims with similar claims in parallel")
                all_relationships = cls._classify_multiple_base_claims_parallel(
                    ai_client, base_claims_with_similar, 'claim', system_prompt
                )
                
                # Store all relationships
                created_count = cls._store_relationships(sql_store, all_relationships)
                stats['relationships_created'] += created_count
                
                # Log cost savings statistics
                if stats['total_pairs'] > 0:
                    savings_percentage = (stats['skipped_pairs'] / stats['total_pairs']) * 100
                    logger.info(f"Regular claims processing complete:")
                    logger.info(f"  - Total pairs considered: {stats['total_pairs']}")
                    logger.info(f"  - Pairs skipped (cost savings): {stats['skipped_pairs']}")
                    logger.info(f"  - Pairs processed: {stats['total_pairs'] - stats['skipped_pairs']}")
                    logger.info(f"  - Cost savings: {savings_percentage:.1f}%")
                    logger.info(f"  - Relationships created: {created_count}")
                else:
                    logger.info(f"Created {created_count} relationships for claims")
        
        except Exception as e:
            logger.error(f"Error in claims processing: {e}")
            stats['errors'] += 1
        
        return stats


if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.INFO)
    stats = ClaimRelationshipClassifier.classify_claim_relationships("both", force_reprocess=False)
    print(f"Processing completed: {stats}")
