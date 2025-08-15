from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from os import getenv
from pathlib import Path
import json
import logging
from datetime import datetime
from timescale_vector.client import uuid_from_time

# Load environment variables from .env file relative to this file's location
current_file = Path(__file__)
env_file = current_file.parent.parent / ".env"
load_dotenv(dotenv_path=env_file)

logger = logging.getLogger(__name__)

class SqlStore:
    def __init__(self):
        self.db_url = getenv("SQL_URL")
        # Create SQLAlchemy engine
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
    

    def insert_data(self, table_name, data):
        """
        Insert data into a table using SQLAlchemy.
        
        Args:
            table_name (str): Name of the table to insert data into
            data (dict): Dictionary where keys are column names and values are data to insert
        """
        if not data:
            raise ValueError("Data dictionary cannot be empty")
        
        # Create column names for the INSERT statement
        columns = list(data.keys())
        
        # Build the INSERT statement
        columns_str = ', '.join(columns)
        placeholders = ', '.join([':' + col for col in columns])
        
        insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
        
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(insert_query), data)
                connection.commit()
                return result.rowcount
        except Exception as e:
            raise Exception(f"Error inserting data into {table_name}: {str(e)}")

    def query_data(self, query):
        pass

    def get_data_by_field(self, table_name, field_name, field_value):
        """
        Get data from a table by a specific field value.
        
        Args:
            table_name (str): Name of the table to query
            field_name (str): Name of the field to search by
            field_value: Value to search for
            
        Returns:
            list: List of dictionaries containing the matching records
        """
        if not table_name or not field_name:
            raise ValueError("Table name and field name cannot be empty")
        
        # Build the SELECT statement
        select_query = f"SELECT * FROM {table_name} WHERE {field_name} = :field_value"
        
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(select_query), {"field_value": field_value})
                rows = result.fetchall()
                
                # Convert to list of dictionaries
                if rows:
                    columns = result.keys()
                    return [dict(zip(columns, row)) for row in rows]
                else:
                    return []
                    
        except Exception as e:
            raise Exception(f"Error querying data from {table_name} where {field_name} = {field_value}: {str(e)}")

    def get_sources_by_metadata_field(self, field_path: str, field_value: str, limit: int = 50):
        """
        Get sources from the database by a specific metadata field value.
        
        Args:
            field_path (str): JSON path to the metadata field (e.g., '$.match_status')
            field_value (str): Value to search for in the metadata field
            limit (int): Maximum number of records to return
            
        Returns:
            list: List of dictionaries containing the matching source records
        """
        if not field_path or not field_value:
            raise ValueError("Field path and field value cannot be empty")
        
        # Convert MySQL-style JSON path to PostgreSQL-style
        # Remove the '$.' prefix and use PostgreSQL JSON operators
        json_key = field_path.replace('$.', '')
        
        # Build the SELECT statement with PostgreSQL JSON extraction
        select_query = f"""
        SELECT * FROM sources 
        WHERE metadata_ ->> :json_key = :field_value
        LIMIT :limit
        """
        
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(select_query), {
                    "json_key": json_key,
                    "field_value": field_value,
                    "limit": limit
                })
                rows = result.fetchall()
                
                # Convert to list of dictionaries
                if rows:
                    columns = result.keys()
                    return [dict(zip(columns, row)) for row in rows]
                else:
                    return []
                    
        except Exception as e:
            raise Exception(f"Error querying sources by metadata field {field_path} = {field_value}: {str(e)}")

    def get_source_by_url(self, url: str):
        """
        Get a source from the database by its URL.
        
        Args:
            url (str): URL to search for
            
        Returns:
            dict: Source dictionary if found, None otherwise
        """
        if not url:
            raise ValueError("URL cannot be empty")
        
        # Build the SELECT statement
        select_query = "SELECT * FROM sources WHERE link = :url LIMIT 1"
        
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(select_query), {"url": url})
                row = result.fetchone()
                
                if row:
                    columns = result.keys()
                    return dict(zip(columns, row))
                else:
                    return None
                    
        except Exception as e:
            raise Exception(f"Error querying source by URL {url}: {str(e)}")

    def delete_data(self, table_name, id):
        """
        Delete a record from a table using SQLAlchemy.
        
        Args:
            table_name (str): Name of the table to delete data from
            id (str): ID of the record to delete
        """
        if not id:
            raise ValueError("ID cannot be empty")
        
        # Build the DELETE statement
        delete_query = f"DELETE FROM {table_name} WHERE id = :id"
        
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(delete_query), {"id": id})
                connection.commit()
                return result.rowcount
        except Exception as e:
            raise Exception(f"Error deleting data from {table_name} with id {id}: {str(e)}")

    def update_data(self, table_name: str, id: str, data: dict) -> int:
        """
        Update a record in a table using SQLAlchemy.
        
        Args:
            table_name (str): Name of the table to update data in
            id (str): ID of the record to update
            data (dict): Dictionary where keys are column names and values are data to update
            
        Returns:
            Number of rows updated
        """
        if not id:
            raise ValueError("ID cannot be empty")
        
        if not data:
            raise ValueError("Data dictionary cannot be empty")
        
        # Build the UPDATE statement
        set_clause = ', '.join([f"{key} = :{key}" for key in data.keys()])
        update_query = f"UPDATE {table_name} SET {set_clause} WHERE id = :id"
        
        # Add the ID to the data dictionary
        update_data = data.copy()
        update_data['id'] = id
        
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(update_query), update_data)
                connection.commit()
                return result.rowcount
        except Exception as e:
            raise Exception(f"Error updating data in {table_name} with id {id}: {str(e)}")

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
            existing_edge = self.get_data_by_field('edges', 'src_id', src_id)
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
            self.insert_data('edges', edge_data)
            logger.debug(f"Created edge {edge_id}: {src_type}:{src_id} -> {dest_type}:{dest_id} ({relationship_type})")
            
            return edge_id
            
        except Exception as e:
            logger.error(f"Error creating edge: {e}")
            return None

    def create_claim(self, claim_data: dict, json_data: dict = None) -> str:
        """
        Create a claim in the database with deduplication logic.
        
        Args:
            claim_data: Dictionary containing claim information
            json_data: Optional JSON data for metadata
            
        Returns:
            The claim ID that was created (or existing claim ID if duplicate)
        """
        try:
            # Helper function to clean None/empty values
            def clean_value(value):
                if value is None or value == '' or value == 'None':
                    return ''
                return str(value)
            
            claim_text = clean_value(claim_data.get('text'))
            if not claim_text:
                logger.warning(f"Skipping claim with no text: {claim_data}")
                return None
            
            # Check for existing claim with same text
            existing_claim = self.get_data_by_field('claims', 'text', claim_text)
            if existing_claim:
                # Use existing claim
                existing_claim_id = existing_claim[0]['id']
                logger.debug(f"Found existing claim {existing_claim_id}")
                return existing_claim_id
            
            # Generate UUID for unique claim ID
            claim_id = str(uuid_from_time(datetime.now()))
            
            # Create claim data for SqlStore
            claim_insert_data = {
                'id': claim_id,
                'text': claim_text,
                'speaker': clean_value(claim_data.get('speaker')),
                'date': clean_value(claim_data.get('published_date')),
                'verified': False,  # Always initialize to False
                'metadata_': json.dumps({
                    'original_claim_id': clean_value(claim_data.get('claim_id')),
                    'canonical_id': clean_value(claim_data.get('canonical_id')),
                    'outlet': clean_value(claim_data.get('outlet')),
                    'matched_source_ids': claim_data.get('matched_source_ids') or [],
                    'judgment': clean_value(claim_data.get('judgment')),
                    'rationale': clean_value(claim_data.get('rationale')),
                    'confidence': clean_value(claim_data.get('confidence')),
                    'tags': claim_data.get('tags') or [],
                    'source_file': clean_value(json_data.get('filename')) if json_data else 'unknown',
                    'source_title': clean_value(json_data.get('title')) if json_data else '',
                    'source_link': clean_value(json_data.get('link')) if json_data else '',
                    'created_at': datetime.now().isoformat()
                })
            }
            
            # Insert claim using SqlStore
            self.insert_data('claims', claim_insert_data)
            logger.debug(f"Created new claim {claim_id}")
            
            return claim_id
            
        except Exception as e:
            logger.error(f"Error creating claim: {e}")
            return None

    def create_source(self, source_data: dict, json_data: dict = None) -> str:
        """
        Create a source in the database with deduplication logic.
        
        Args:
            source_data: Dictionary containing source information
            json_data: Optional JSON data for metadata
            
        Returns:
            The source ID that was created (or existing source ID if duplicate)
        """
        try:
            # Helper function to clean None/empty values
            def clean_value(value):
                if value is None or value == '' or value == 'None':
                    return ''
                return str(value)
            
            source_title = clean_value(source_data.get('title'))
            source_url = clean_value(source_data.get('url'))
            match_status = clean_value(source_data.get('match_status', ''))
            
            # Initialize variables that might be used later
            description = source_title
            publisher = clean_value(source_data.get('publisher_or_court'))
            search_queries = source_data.get('search_query') or []
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
                    logger.warning(f"Skipping source with no URL and no identifying information: {source_data}")
                    return None
            
            # Check for existing source with same URL only
            existing_source = self.get_data_by_field('sources', 'link', source_url)
            if existing_source:
                existing_source_id = existing_source[0]['id']
                logger.debug(f"Found existing source {existing_source_id}")
                return existing_source_id
            
            # Generate UUID for unique source ID
            source_id = str(uuid_from_time(datetime.now()))
            
            # Create source data for SqlStore
            source_insert_data = {
                'id': source_id,
                'description': source_title,  # Already converted None to empty string
                'link': source_url,  # Use the URL (real or synthetic)
                'verified': False,  # Always initialize to False
                'metadata_': json.dumps({
                    'original_source_id': clean_value(source_data.get('source_id')),
                    'source_type': clean_value(source_data.get('source_type')),
                    'publisher_or_court': publisher,  # Already cleaned
                    'match_status': clean_value(source_data.get('match_status')),
                    'search_query': search_queries,  # Already cleaned
                    'source_file': clean_value(json_data.get('filename')) if json_data else 'unknown',
                    'source_title': clean_value(json_data.get('title')) if json_data else '',
                    'source_link': clean_value(json_data.get('link')) if json_data else '',
                    'created_at': datetime.now().isoformat()
                })
            }
            
            # Insert source using SqlStore
            self.insert_data('sources', source_insert_data)
            logger.debug(f"Created new source {source_id}")
            
            return source_id
            
        except Exception as e:
            logger.error(f"Error creating source: {e}")
            return None