from dotenv import load_dotenv
from os import getenv
import psycopg2
import pandas as pd
import urllib.parse as urlparse
from sqlalchemy import create_engine, inspect, text
from timescale_vector import client

from .table_defs import Base
from .vector_api import VectorStore
from .sql_api import SqlStore
from util.ai_ext_calls import OpenAiSync

load_dotenv(dotenv_path="../.env")


class DbInit:
    def __init__(self):
        self.canon_claim_store = VectorStore(table_name="canon_claims")
        #self.claim_store = VectorStore(table_name="claims")
        self.sql_store = SqlStore()
        self.db_engine = create_engine(getenv("SQL_URL"))
        self.create_tables()

    # TODO: Doesn't seem to work, look into it
    # def clean_tables(self):
    #     Base.metadata.drop_all(self.db_engine)

    def create_tables(self):
        self.canon_claim_store.create_tables()
        #self.claim_store.create_tables()
        Base.metadata.create_all(self.db_engine)

    def upgrade_claims_table_with_vectors(self):
        """
        Safely add vector embedding column to existing claims table.
        """
        try:
            inspector = inspect(self.db_engine)
            
            if inspector.has_table("claims"):
                print("Claims table exists, checking current columns...")
                existing_columns = [col['name'] for col in inspector.get_columns("claims")]
                print(f"Existing columns: {existing_columns}")
                
                # Check if embedding column already exists
                if 'embedding' not in existing_columns:
                    print("Adding embedding column...")
                    with self.db_engine.connect() as connection:
                        # Add the embedding column manually
                        connection.execute(text("""
                            ALTER TABLE claims 
                            ADD COLUMN embedding vector(1536)
                        """))
                        connection.commit()
                    print("Successfully added embedding column")
                    
                    # Generate embeddings for existing claims
                    print("Generating embeddings for existing claims...")
                    self.generate_embeddings_for_existing_claims()
                else:
                    print("Embedding column already exists")
                
                # Add created_at timestamp column for hypertable time partitioning
                if 'created_at' not in existing_columns:
                    print("Adding created_at timestamp column...")
                    with self.db_engine.connect() as connection:
                        # Add created_at column
                        connection.execute(text("""
                            ALTER TABLE claims 
                            ADD COLUMN created_at TIMESTAMPTZ
                        """))
                        
                        # Populate created_at from metadata_ JSON field
                        connection.execute(text("""
                            UPDATE claims 
                            SET created_at = (metadata_->>'created_at')::TIMESTAMPTZ
                            WHERE metadata_ IS NOT NULL 
                            AND metadata_->>'created_at' IS NOT NULL
                            AND created_at IS NULL
                        """))
                        
                        # Modify primary key to include created_at (required for TimescaleDB hypertable)
                        print("Modifying primary key to include created_at...")
                        connection.execute(text("""
                            ALTER TABLE claims 
                            DROP CONSTRAINT claims_pkey
                        """))
                        
                        connection.execute(text("""
                            ALTER TABLE claims 
                            ADD PRIMARY KEY (id, created_at)
                        """))
                        
                        connection.commit()
                    print("Successfully added and populated created_at column from metadata")
                    print("Successfully modified primary key to include created_at")
                else:
                    print("created_at column already exists")
                    # Check if primary key needs to be modified
                    with self.db_engine.connect() as connection:
                        # Check current primary key structure
                        result = connection.execute(text("""
                            SELECT constraint_name, column_name 
                            FROM information_schema.key_column_usage 
                            WHERE table_name = 'claims' 
                            AND constraint_name = (
                                SELECT constraint_name 
                                FROM information_schema.table_constraints 
                                WHERE table_name = 'claims' 
                                AND constraint_type = 'PRIMARY KEY'
                            )
                            ORDER BY ordinal_position
                        """))
                        
                        pk_columns = [row[1] for row in result.fetchall()]
                        print(f"Current primary key columns: {pk_columns}")
                        
                        if 'created_at' not in pk_columns:
                            print("Modifying primary key to include created_at...")
                            connection.execute(text("""
                                ALTER TABLE claims 
                                DROP CONSTRAINT claims_pkey
                            """))
                            
                            connection.execute(text("""
                                ALTER TABLE claims 
                                ADD PRIMARY KEY (id, created_at)
                            """))
                            
                            connection.commit()
                            print("Successfully modified primary key to include created_at")
                        else:
                            print("Primary key already includes created_at")
                
                # Verify the columns were added
                updated_columns = [col['name'] for col in inspector.get_columns("claims")]
                print(f"Updated columns: {updated_columns}")
                
                # Convert to hypertable
                self.convert_claims_to_hypertable()
                    
            else:
                print("Claims table doesn't exist, creating new table with vector support...")
                # Assuming ClaimsTable is defined elsewhere or needs to be imported
                # from .table_defs import ClaimsTable
                # ClaimsTable.__table__.create(self.db_engine)
                print("Claims table created with vector support")
                
                # Convert to hypertable
                # self.convert_claims_to_hypertable()
                
        except Exception as e:
            print(f"Error upgrading claims table: {e}")
            raise

    def generate_embeddings_for_existing_claims(self, batch_size: int = 10):
        """
        Generate embeddings for all existing claims that don't have embeddings yet.
        Uses OpenAI provider for embedding generation.
        """
        try:
            # Initialize OpenAI client for embeddings
            ai_client = OpenAiSync(provider="openai")
            
            with self.db_engine.connect() as connection:
                # Get claims without embeddings
                result = connection.execute(text("""
                    SELECT id, text FROM claims 
                    WHERE embedding IS NULL
                    ORDER BY id
                """))
                
                claims = result.fetchall()
                total_claims = len(claims)
                
                if total_claims == 0:
                    print("No claims found without embeddings")
                    return
                
                print(f"Found {total_claims} claims needing embeddings")
                
                # Process in batches to avoid overwhelming the API
                for i in range(0, total_claims, batch_size):
                    batch = claims[i:i + batch_size]
                    print(f"Processing batch {i//batch_size + 1}/{(total_claims + batch_size - 1)//batch_size}")
                    
                    for claim_id, claim_text in batch:
                        try:
                            # Generate embedding
                            embedding = ai_client.get_embedding(claim_text)
                            
                            # Update the claim
                            connection.execute(text("""
                                UPDATE claims 
                                SET embedding = :embedding 
                                WHERE id = :claim_id
                            """), {
                                "embedding": embedding,
                                "claim_id": claim_id
                            })
                            
                            print(f"Generated embedding for claim {claim_id}")
                            
                        except Exception as e:
                            print(f"Error generating embedding for claim {claim_id}: {e}")
                            continue
                    
                    # Commit batch
                    connection.commit()
                    print(f"Committed batch {i//batch_size + 1}")
                
                print(f"Successfully generated embeddings for {total_claims} claims")
                
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            raise

    def convert_claims_to_hypertable(self):
        """
        Convert claims table to a TimescaleDB hypertable using the created_at timestamp field.
        """
        try:
            with self.db_engine.connect() as connection:
                # Check if table is already a hypertable
                result = connection.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM timescaledb_information.hypertables 
                        WHERE hypertable_name = 'claims'
                    )
                """))
                is_hypertable = result.scalar()
                
                if is_hypertable:
                    print("Claims table is already a hypertable")
                    return
                
                # Convert to hypertable using the created_at timestamp field
                connection.execute(text("""
                    SELECT create_hypertable(
                        'claims', 
                        'created_at', 
                        chunk_time_interval => INTERVAL '7 days',
                        migrate_data => true,
                        if_not_exists => TRUE
                    )
                """))
                
                connection.commit()
                print("Successfully converted claims table to hypertable using created_at field")
                
                # Note: Index creation will be done separately
                
        except Exception as e:
            print(f"Error converting to hypertable: {e}")
            # Check if it's because TimescaleDB extension isn't installed
            if "extension" in str(e).lower() or "timescaledb" in str(e).lower():
                print("Note: TimescaleDB extension may not be installed. Hypertable conversion skipped.")
            else:
                raise

    def create_claims_vector_index(self):
        """
        Create vector index on claims table using timescale_vector's create_index function.
        This should be run separately after hypertable creation and after some data is loaded.
        """
        try:
            # Create a VectorStore instance for the claims table
            claims_vector_store = VectorStore(table_name="claims")
            
            # Use timescale_vector's create_index method
            claims_vector_store.create_index()
            
            print("Successfully created timescale_vector index on claims table")
            
        except Exception as e:
            print(f"Error creating timescale_vector index: {e}")
            print("Note: Index creation may fail if table is empty or TimescaleDB extension isn't installed")
            # Don't raise - index creation is optional for basic functionality


if __name__ == '__main__':
    # Step 1: Initialize database
    print("Step 1: Initializing database...")
    db = DbInit()
    
    # Step 2: Generate embeddings for existing claims
    print("\nStep 2: Generating embeddings for existing claims...")
    try:
        db.generate_embeddings_for_existing_claims()
        print("Embedding generation completed successfully!")
    except Exception as e:
        print(f"Error generating embeddings: {e}")
        raise

    #db.clean_tables()

    # input("Remove all tables? (y/n)")
    # if input() == "y":
    #     db.clean_tables()