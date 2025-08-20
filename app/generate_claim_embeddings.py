#!/usr/bin/env python3
"""
Script to generate embeddings for existing claims that don't have them.
This script will:
1. Find all claims in the database that have null embeddings
2. Generate embeddings for them using the AI client
3. Update the database with the new embeddings
"""

import sys
import os
import logging
import time
from pathlib import Path
from typing import List, Dict, Any

# Add the app directory to the Python path
app_dir = Path(__file__).parent
sys.path.insert(0, str(app_dir))

from database.sql_api import SqlStore
from util.ai_ext_calls import OpenAiSync

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_claims_without_embeddings(sql_store: SqlStore) -> List[Dict[str, Any]]:
    """
    Get all claims that don't have embeddings.
    
    Args:
        sql_store: SqlStore instance
        
    Returns:
        List of claim dictionaries without embeddings
    """
    try:
        with sql_store.engine.connect() as connection:
            from sqlalchemy import text
            
            query = text("""
                SELECT id, contents, speaker, date, verified, created_at, metadata
                FROM claims 
                WHERE embedding IS NULL
                ORDER BY created_at DESC
            """)
            
            result = connection.execute(query)
            claims = []
            
            for row in result:
                claim = {
                    'id': row[0],
                    'contents': row[1],
                    'speaker': row[2],
                    'date': row[3],
                    'verified': row[4],
                    'created_at': row[5],
                    'metadata': row[6]
                }
                claims.append(claim)
            
            return claims
            
    except Exception as e:
        logger.error(f"Error getting claims without embeddings: {e}")
        return []

def update_claim_embedding(sql_store: SqlStore, claim_id: str, embedding: List[float]) -> bool:
    """
    Update a claim with its embedding.
    
    Args:
        sql_store: SqlStore instance
        claim_id: ID of the claim to update
        embedding: The embedding vector
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with sql_store.engine.connect() as connection:
            from sqlalchemy import text
            
            query = text("""
                UPDATE claims 
                SET embedding = :embedding
                WHERE id = :claim_id
            """)
            
            result = connection.execute(query, {
                'embedding': embedding,
                'claim_id': claim_id
            })
            
            connection.commit()
            return result.rowcount > 0
            
    except Exception as e:
        logger.error(f"Error updating claim {claim_id} with embedding: {e}")
        return False

def generate_embeddings_for_claims(batch_size: int = 10, delay_seconds: float = 1.0):
    """
    Generate embeddings for claims that don't have them.
    
    Args:
        batch_size: Number of claims to process in each batch
        delay_seconds: Delay between batches to avoid rate limiting
    """
    logger.info("Starting embedding generation for claims")
    
    try:
        # Initialize components
        sql_store = SqlStore()
        ai_client = OpenAiSync(provider="openai")
        
        # Get claims without embeddings
        claims = get_claims_without_embeddings(sql_store)
        
        if not claims:
            logger.info("No claims found without embeddings")
            return
        
        logger.info(f"Found {len(claims)} claims without embeddings")
        
        # Process claims in batches
        total_processed = 0
        total_errors = 0
        
        for i in range(0, len(claims), batch_size):
            batch = claims[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(claims) + batch_size - 1) // batch_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} claims)")
            
            batch_processed = 0
            batch_errors = 0
            
            for claim in batch:
                try:
                    # Generate embedding
                    embedding = ai_client.get_embedding(claim['contents'])
                    
                    # Update the claim
                    if update_claim_embedding(sql_store, claim['id'], embedding):
                        batch_processed += 1
                        logger.debug(f"Generated embedding for claim {claim['id']}")
                    else:
                        batch_errors += 1
                        logger.error(f"Failed to update claim {claim['id']} with embedding")
                        
                except Exception as e:
                    batch_errors += 1
                    logger.error(f"Error generating embedding for claim {claim['id']}: {e}")
                    continue
            
            total_processed += batch_processed
            total_errors += batch_errors
            
            logger.info(f"Batch {batch_num} complete: {batch_processed} processed, {batch_errors} errors")
            
            # Add delay between batches to avoid rate limiting
            if i + batch_size < len(claims):
                logger.info(f"Waiting {delay_seconds} seconds before next batch...")
                time.sleep(delay_seconds)
        
        logger.info(f"Embedding generation complete:")
        logger.info(f"  - Total claims processed: {total_processed}")
        logger.info(f"  - Total errors: {total_errors}")
        logger.info(f"  - Success rate: {(total_processed / len(claims)) * 100:.1f}%")
        
    except Exception as e:
        logger.error(f"Error in embedding generation process: {e}")
        sys.exit(1)

def main():
    """Main function to run the embedding generation."""
    print("=" * 60)
    print("CLAIM EMBEDDING GENERATION SCRIPT")
    print("=" * 60)
    print()
    print("This script will generate embeddings for all claims")
    print("in the database that currently have null embeddings.")
    print()
    
    # Get user input for batch size and delay
    try:
        batch_size = int(input("Enter batch size (default 10): ") or "10")
        delay_seconds = float(input("Enter delay between batches in seconds (default 1.0): ") or "1.0")
    except ValueError:
        print("Invalid input, using defaults: batch_size=10, delay=1.0")
        batch_size = 10
        delay_seconds = 1.0
    
    print()
    print(f"Configuration:")
    print(f"  - Batch size: {batch_size}")
    print(f"  - Delay between batches: {delay_seconds} seconds")
    print()
    
    # Confirm with user
    response = input("Proceed with embedding generation? (yes/no): ")
    if response.lower() != 'yes':
        print("Embedding generation cancelled.")
        return
    
    print()
    print("Starting embedding generation...")
    print("=" * 60)
    
    # Run the embedding generation
    generate_embeddings_for_claims(batch_size, delay_seconds)
    
    print()
    print("=" * 60)
    print("Embedding generation complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
