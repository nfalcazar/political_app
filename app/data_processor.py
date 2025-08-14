import json
import os
import logging
import multiprocessing as mp
from pathlib import Path
from typing import List, Dict, Any, Optional
from database.table_defs import Base, ClaimsTable, SourcesTable, EdgeTable
from database.vector_api import VectorStore
from database.sql_api import SqlStore
from util.ai_ext_calls import OpenAiSync
from timescale_vector.client import uuid_from_time
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

class DataProcessor(mp.Process):
    """
    A class that processes JSON files from the data directory and updates database tables.
    Handles the logic for updating canon claims, claims, and sources tables.
    """
    
    def __init__(self, json_queue: mp.Queue, data_dir: str = "/home/nalc/political_app/data", 
                 db_url: Optional[str] = None):
        """
        Initialize the DataProcessor.
        
        Args:
            json_queue: Multiprocessing queue containing JSON objects to process
            data_dir: Path to the directory containing JSON files (for backward compatibility)
            db_url: Database connection URL. If None, will use environment variable
        """
        super().__init__()
        self.json_queue = json_queue
        self.data_dir = Path(data_dir)
        try:
            self.ai_client = OpenAiSync(provider="openai")
        except Exception as e:
            logger.error(f"Error initializing OpenAiSync: {e}")
            raise
        
        # Initialize VectorStore for canonical claims
        self.vector_store = VectorStore("canon_claims")
        
        # Initialize SqlStore for other tables
        self.sql_store = SqlStore()
        

    
    def run(self):
        """
        Main process method that continuously processes JSON objects from the queue.
        Stops when None is encountered (sentinel value).
        """
        logger.info("DataProcessor process started")
        
        while True:
            try:
                # Get item from queue
                item = self.json_queue.get()
                
                # Check for sentinel value to stop processing
                if item is None:
                    logger.info("Received sentinel value, stopping DataProcessor")
                    break
                
                # Process the JSON object
                try:
                    results = self.process_json(item)
                except Exception as e:
                    logger.error(f"Error processing JSON object: {e}")
                    continue
                    
            except Exception as e:
                logger.error(f"Error in DataProcessor run loop: {e}")
                continue
        
        logger.info("DataProcessor process finished")
    
    def process_json(self, json_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Process a single JSON object and update all relevant database tables.
        
        Args:
            json_data: JSON object containing canonical_claims, claims, and sources
            
        Returns:
            Dictionary with counts of processed records for each table type
        """
        logger.debug("Processing JSON object")
        
        # Process canonical claims with vector store
        processed_canon_data = self.process_canonical_claims(json_data)
        canon_claim_ids = processed_canon_data['ids']
        canonical_claim_map = processed_canon_data['canonical_claim_map']
        
        # Process other tables with SqlStore
        try:
            # Process each table type
            claim_data = self.process_claims(json_data)
            source_data = self.process_sources(json_data)
            
            # Create edges for canonical claims and claims (references relationship)
            references_edges_created = 0
            for original_canon_id, new_canon_id in canonical_claim_map.items():
                # Find claims that reference this canonical claim
                for original_claim_id, claim_info in claim_data['claim_map'].items():
                    if claim_info['canonical_id'] == original_canon_id:
                        try:
                            self.create_edge(
                                'canonical_claim', 
                                new_canon_id, 
                                'claim', 
                                claim_info['new_id'],
                                'references'
                            )
                            references_edges_created += 1
                        except Exception as e:
                            logger.error(f"Error creating canonical_claim to claim edge: {e}")
                            continue
            
            # Create edges for claims and sources (cites relationship)
            cites_edges_created = 0
            for original_claim_id, claim_info in claim_data['claim_map'].items():
                # Get the matched source IDs from the original claim
                original_claim = next((c for c in json_data['claims'] if c.get('claim_id') == original_claim_id), None)
                if original_claim:
                    matched_source_ids = original_claim.get('matched_source_ids', [])
                    for source_id in matched_source_ids:
                        # Find the corresponding new source ID
                        if source_id in source_data['source_map']:
                            new_source_id = source_data['source_map'][source_id]
                            try:
                                self.create_edge(
                                    'claim',
                                    claim_info['new_id'],
                                    'source',
                                    new_source_id,
                                    'cites'
                                )
                                cites_edges_created += 1
                            except Exception as e:
                                logger.error(f"Error creating claim to source edge: {e}")
                                continue
            
            logger.debug(f"Successfully processed JSON object: "
                      f"{len(canon_claim_ids)} canonical claims, "
                      f"{len(claim_data['ids'])} claims, "
                      f"{len(source_data['ids'])} sources, "
                      f"{references_edges_created} references edges, "
                      f"{cites_edges_created} cites edges")
            
            return {
                'canonical_claims': canon_claim_ids,
                'claims': claim_data['ids'],
                'sources': source_data['ids']
            }
                
        except Exception as e:
            logger.error(f"Error processing JSON object: {e}")
            raise
        
    def get_json_files(self) -> List[Path]:
        """
        Get all JSON files from the data directory.
        
        Returns:
            List of Path objects for JSON files
        """
        json_files = list(self.data_dir.glob("*.json"))
        logger.info(f"Found {len(json_files)} JSON files in {self.data_dir}")
        return json_files
    
    def load_json_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Load and parse a JSON file.
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            Parsed JSON data as dictionary
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Successfully loaded {file_path}")
            return data
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            raise
    
    def create_edge(self, src_type: str, src_id: str, dest_type: str, dest_id: str, relationship_type: str, metadata: dict = None) -> str:
        """
        Create an edge between two entities in the database.
        Includes deduplication to prevent duplicate edges.
        
        Args:
            src_type: Source entity type (e.g., 'canonical_claim', 'claim', 'source')
            src_id: Source entity ID
            dest_type: Destination entity type
            dest_id: Destination entity ID
            relationship_type: Type of relationship (e.g., 'supports', 'refutes', 'extracted_from', 'cited_by')
            metadata: Additional metadata for the edge
            
        Returns:
            The edge ID that was created (or existing edge ID if duplicate)
        """
        try:
            # Check if edge already exists
            existing_edge = self.sql_store.get_data_by_field('edges', 'src_id', src_id)
            if existing_edge:
                # Check if any existing edge matches the destination and relationship
                for edge in existing_edge:
                    if (edge.get('dest_id') == dest_id and 
                        edge.get('dest_type') == dest_type and 
                        edge.get('relationship_type') == relationship_type):
                        logger.debug(f"Edge already exists: {src_type}:{src_id} -> {dest_type}:{dest_id} ({relationship_type})")
                        return edge['id']
            
            # Generate UUID for edge ID
            edge_id = str(uuid_from_time(datetime.now()))
            
            # Prepare metadata
            edge_metadata = metadata or {}
            edge_metadata['created_at'] = datetime.now().isoformat()
            
            # Create edge data for SqlStore
            edge_data = {
                'id': edge_id,
                'src_type': src_type,
                'src_id': src_id,
                'dest_type': dest_type,
                'dest_id': dest_id,
                'relationship_type': relationship_type,
                'metadata_': json.dumps(edge_metadata) # Convert dictionary to JSON string
            }
            
            # Insert edge using SqlStore
            self.sql_store.insert_data('edges', edge_data)
            logger.debug(f"Created edge {edge_id}: {src_type}:{src_id} -> {dest_type}:{dest_id} ({relationship_type})")
            
            return edge_id
            
        except Exception as e:
            logger.error(f"Error creating edge: {e}")
            return None

    def process_canonical_claims(self, json_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Process canonical claims from JSON data and insert into vector database.
        Uses vector search to avoid duplicates.
        
        Args:
            json_data: Parsed JSON data
            
        Returns:
            Dictionary with processed IDs and their metadata for edge creation
        """
        processed_data = {
            'ids': [],
            'canonical_claim_map': {}  # Maps original canonical_id to new UUID
        }
        
        if 'canonical_claims' not in json_data:
            logger.warning("No canonical_claims found in JSON data")
            return processed_data
        
        # Prepare data for vector store upsert
        records_data = []
        
        for canon_claim in json_data['canonical_claims']:
            try:
                # Extract content (text field)
                content = canon_claim.get('text', '')
                if not content:
                    logger.warning(f"Skipping canonical claim with no text: {canon_claim}")
                    continue
                
                # Generate embedding
                try:
                    embedding = self.ai_client.get_embedding(content)
                except Exception as e:
                    logger.error(f"Failed to generate embedding for canonical claim: {e}")
                    # Skip this claim if embedding fails
                    continue
                
                # Search for similar existing canonical claims
                try:
                    similar_claims = self.vector_store.search_by_text(
                        content, 
                        limit=1, 
                        return_dataframe=True
                    )
                    
                    # If we found a similar claim with high similarity, use that instead
                    if not similar_claims.empty:
                        best_match = similar_claims.iloc[0]
                        similarity_score = best_match.get('distance', 1.0)  # Lower distance = higher similarity
                        
                        # Threshold for considering claims similar (adjust as needed)
                        similarity_threshold = 0.18  # Lower threshold = more strict matching
                        
                        if similarity_score < similarity_threshold:
                            # Use existing canonical claim
                            existing_canon_id = best_match['id']
                            logger.info(f"Found similar canonical claim {existing_canon_id} (similarity: {similarity_score:.3f})")
                            
                            # Store mapping from original canonical_id to existing UUID
                            original_canon_id = canon_claim.get('canonical_id', '')
                            if original_canon_id:
                                processed_data['canonical_claim_map'][original_canon_id] = existing_canon_id
                            
                            continue  # Skip creating new canonical claim
                            
                except Exception as e:
                    logger.warning(f"Error searching for similar canonical claims: {e}")
                    # Continue with creating new canonical claim
                
                # Generate new UUID for new canonical claim
                canon_id = str(uuid_from_time(datetime.now()))
                
                # Create metadata with all other fields
                metadata = {}
                for key, value in canon_claim.items():
                    if key != 'text':  # Exclude the text field as it goes to content
                        metadata[key] = value
                
                # Add source file information to metadata
                metadata['source_file'] = json_data.get('filename', 'unknown')
                metadata['source_title'] = json_data.get('title', '')
                metadata['source_link'] = json_data.get('link', '')
                metadata['created_at'] = datetime.now().isoformat()
                metadata['verified'] = False
                
                # Prepare record for vector store
                record = {
                    'id': canon_id,
                    'metadata_': metadata,
                    'contents': content,
                    'embedding': embedding
                }
                
                records_data.append(record)
                processed_data['ids'].append(canon_id)
                
                # Store mapping from original canonical_id to new UUID for edge creation
                original_canon_id = canon_claim.get('canonical_id', '')
                if original_canon_id:
                    processed_data['canonical_claim_map'][original_canon_id] = canon_id
                
                logger.debug(f"Prepared new canonical claim {canon_id}: {content[:100]}...")
                
            except Exception as e:
                logger.error(f"Error processing canonical claim: {e}")
                continue
        
        # Upsert all new records to vector store
        if records_data:
            try:
                df = pd.DataFrame(records_data)
                self.vector_store.upsert(df)
                logger.debug(f"Successfully upserted {len(records_data)} new canonical claims to vector store")
            except Exception as e:
                logger.error(f"Error upserting canonical claims to vector store: {e}")
                logger.error(f"Vector store error details: {str(e)}")
                # Don't reset the counter, just log the error and continue
                # The records were prepared successfully, just the upsert failed
        
        return processed_data
    
    def process_claims(self, json_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Process claims from JSON data and insert into database.
        Uses content-based deduplication to avoid duplicates.
        
        Args:
            json_data: Parsed JSON data
            session: Database session
            
        Returns:
            Dictionary with processed IDs and their metadata for edge creation
        """
        processed_data = {
            'ids': [],
            'claim_map': {}  # Maps original claim_id to new UUID and canonical_id
        }
        
        if 'claims' not in json_data:
            logger.warning("No claims found in JSON data")
            return processed_data
        
        # Helper function to clean None/empty values
        def clean_value(value):
            if value is None or value == '' or value == 'None':
                return ''
            return str(value)
        
        for claim in json_data['claims']:
            
            claim_text = clean_value(claim.get('text'))
            if not claim_text:
                logger.warning(f"Skipping claim with no text: {claim}")
                continue
            
            # Check for existing claim with same text
            existing_claim_id = None
            try:
                existing_claim = self.sql_store.get_data_by_field('claims', 'text', claim_text)
                if existing_claim:
                    # Use existing claim
                    existing_claim_id = existing_claim[0]['id']
                    logger.debug(f"Found existing claim {existing_claim_id}")
                else:
                    logger.debug(f"No existing claim found")
                
                if existing_claim_id:
                    # Store mapping for edge creation
                    original_claim_id = clean_value(claim.get('claim_id'))
                    canonical_id = clean_value(claim.get('canonical_id'))
                    if original_claim_id:
                        processed_data['claim_map'][original_claim_id] = {
                            'new_id': existing_claim_id,
                            'canonical_id': canonical_id
                        }
                    
                    continue  # Skip creating new claim
                    
            except Exception as e:
                logger.warning(f"Error checking for existing claim: {e}")
                # Continue with creating new claim
            
            # Generate UUID for unique claim ID
            claim_id = str(uuid_from_time(datetime.now()))
            
            # Create claim data for SqlStore
            claim_data = {
                'id': claim_id,
                'text': claim_text,
                'speaker': clean_value(claim.get('speaker')),
                'date': clean_value(claim.get('published_date')),
                'verified': False,  # Always initialize to False
                'metadata_': json.dumps({
                    'original_claim_id': clean_value(claim.get('claim_id')),
                    'canonical_id': clean_value(claim.get('canonical_id')),
                    'outlet': clean_value(claim.get('outlet')),
                    'matched_source_ids': claim.get('matched_source_ids') or [],
                    'judgment': clean_value(claim.get('judgment')),
                    'rationale': clean_value(claim.get('rationale')),
                    'confidence': clean_value(claim.get('confidence')),
                    'tags': claim.get('tags') or [],
                    'source_file': clean_value(json_data.get('filename')) or 'unknown',
                    'source_title': clean_value(json_data.get('title')),
                    'source_link': clean_value(json_data.get('link')),
                    'created_at': datetime.now().isoformat()
                })
            }
            
            # Insert claim using SqlStore
            try:
                self.sql_store.insert_data('claims', claim_data)
                processed_data['ids'].append(claim_id)
                
                # Store mapping for edge creation
                original_claim_id = claim.get('claim_id', '')
                canonical_id = claim.get('canonical_id', '')
                if original_claim_id:
                    processed_data['claim_map'][original_claim_id] = {
                        'new_id': claim_id,
                        'canonical_id': canonical_id
                    }
                
                logger.debug(f"Processed new claim {claim_id}")
            except Exception as e:
                logger.error(f"Error inserting claim {claim_id}: {e}")
                continue
        
        return processed_data
    
    def process_sources(self, json_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Process sources from JSON data and insert into database.
        Uses content-based deduplication to avoid duplicates.
        
        Args:
            json_data: Parsed JSON data
            session: Database session
            
        Returns:
            Dictionary with processed IDs and their metadata for edge creation
        """
        processed_data = {
            'ids': [],
            'source_map': {}  # Maps original source_id to new UUID
        }
        
        if 'sources' not in json_data:
            logger.warning("No sources found in JSON data")
            return processed_data
        
        # Helper function to clean None/empty values
        def clean_value(value):
            if value is None or value == '' or value == 'None':
                return ''
            return str(value)
        
        for source in json_data['sources']:
            
            source_title = clean_value(source.get('title'))
            source_url = clean_value(source.get('url'))
            match_status = clean_value(source.get('match_status', ''))
            
            # Initialize variables that might be used later
            description = source_title
            publisher = clean_value(source.get('publisher_or_court'))
            search_queries = source.get('search_query') or []
            if search_queries is None:
                search_queries = []
            
            # If source_url is missing or match_status is "unresolved", create a synthetic URL
            if not source_url or match_status == "unresolved":
                
                # Combine all components into a synthetic URL
                components = []
                if description:
                    components.append(description)
                if publisher:
                    components.append(publisher)
                if search_queries:
                    components.extend(search_queries)
                
                if components:
                    source_url = ' '.join(components).strip()
                    if match_status == "unresolved":
                        logger.debug(f"Created synthetic URL for unresolved source: {source_url}")
                    else:
                        logger.debug(f"Created synthetic URL for source with missing URL: {source_url}")
                else:
                    logger.warning(f"Skipping source with no URL and no identifying information: {source}")
                    continue
            
            # Check for existing source with same URL only
            existing_source_id = None
            try:
                existing_source = self.sql_store.get_data_by_field('sources', 'link', source_url)
                if existing_source:
                    existing_source_id = existing_source[0]['id']
                    logger.debug(f"Found existing source {existing_source_id}")
                else:
                    logger.debug(f"No existing source found for URL")
                
                if existing_source_id:
                    # Store mapping for edge creation
                    original_source_id = source.get('source_id', '')
                    if original_source_id:
                        processed_data['source_map'][original_source_id] = existing_source_id
                    
                    continue  # Skip creating new source
                    
            except Exception as e:
                logger.warning(f"Error checking for existing source: {e}")
                # Continue with creating new source
            
            # Generate UUID for unique source ID
            source_id = str(uuid_from_time(datetime.now()))
            
            # Create source data for SqlStore
            source_data = {
                'id': source_id,
                'description': source_title,  # Already converted None to empty string
                'link': source_url,  # Use the URL (real or synthetic)
                'verified': False,  # Always initialize to False
                'metadata_': json.dumps({
                    'original_source_id': clean_value(source.get('source_id')),
                    'source_type': clean_value(source.get('source_type')),
                    'publisher_or_court': publisher,  # Already cleaned
                    'match_status': clean_value(source.get('match_status')),
                    'search_query': search_queries,  # Already cleaned
                    'source_file': clean_value(json_data.get('filename')) or 'unknown',
                    'source_title': clean_value(json_data.get('title')),
                    'source_link': clean_value(json_data.get('link')),
                    'created_at': datetime.now().isoformat()
                })
            }
            
            # Insert source using SqlStore
            try:
                self.sql_store.insert_data('sources', source_data)
                processed_data['ids'].append(source_id)
                
                # Store mapping for edge creation
                original_source_id = source.get('source_id', '')
                if original_source_id:
                    processed_data['source_map'][original_source_id] = source_id
                
                logger.debug(f"Processed new source {source_id}")
            except Exception as e:
                logger.error(f"Error inserting source {source_id}: {e}")
                continue
        
        return processed_data
    
    def process_json_file(self, file_path: Path) -> Dict[str, List[str]]:
        """
        Process a single JSON file and update all relevant database tables.
        
        Args:
            file_path: Path to the JSON file to process
            
        Returns:
            Dictionary with counts of processed records for each table type
        """
        logger.info(f"Processing file: {file_path}")
        
        # Load JSON data
        json_data = self.load_json_file(file_path)
        
        # Use the process_json method to avoid code duplication
        return self.process_json(json_data)
    
    def process_all_files(self) -> Dict[str, int]:
        """
        Process all JSON files in the data directory.
        
        Returns:
            Dictionary with total counts of processed records for each table type
        """
        json_files = self.get_json_files()
        total_counts = {
            'canonical_claims': 0,
            'claims': 0,
            'sources': 0,
            'files_processed': 0,
            'files_failed': 0
        }
        
        for file_path in json_files:
            try:
                results = self.process_json_file(file_path)
                total_counts['canonical_claims'] += len(results['canonical_claims'])
                total_counts['claims'] += len(results['claims'])
                total_counts['sources'] += len(results['sources'])
                total_counts['files_processed'] += 1
                
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                total_counts['files_failed'] += 1
                continue
        
        logger.info(f"Processing complete. Summary: {total_counts}")
        return total_counts
    



def main():
    """Main function to run the data processor."""
    # Set up logging
    # logging.basicConfig(
    #     level=logging.INFO,
    #     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    # )
    
    # Example of using the multiprocessing DataProcessor
    json_queue = mp.Queue()
    
    # Initialize the processor
    processor = DataProcessor(json_queue)
    
    # Start the processor
    processor.start()
    
    # Example: Load some JSON files and put them in the queue
    data_processor = DataProcessor(json_queue)  # Temporary instance for file operations
    json_files = data_processor.get_json_files()
    
    for file_path in json_files:  # Process first 3 files as example
        try:
            json_data = data_processor.load_json_file(file_path)
            json_queue.put(json_data)
            print(f"Added {file_path} to queue")
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    # Send sentinel value to stop processing
    json_queue.put(None)
    
    # Wait for processor to finish
    processor.join()
    
    print("Processing complete")


if __name__ == "__main__":
    main()
