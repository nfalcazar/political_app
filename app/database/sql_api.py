from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from os import getenv
from pathlib import Path

# Load environment variables from .env file relative to this file's location
current_file = Path(__file__)
env_file = current_file.parent.parent / ".env"
load_dotenv(dotenv_path=env_file)

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