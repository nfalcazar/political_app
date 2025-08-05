import table_defs
import psycopg2
import pandas as pd
import urllib.parse as urlparse
from sqlalchemy import create_engine, inspect
from timescale_vector import client
from settings import get_settings

from vector_api import VectorStore
from sql_api import SqlStore

class DbInit:
    def __init__(self):
        self.settings = get_settings()
        self.vec_store = VectorStore()
        self.sql_store = SqlStore()
        self.db_url = "postgresql://postgres:password@localhost:5432/postgres"
        self.db_engine = create_engine(self.db_url)


    def clean_tables(self):
        table_defs.Base.metadata.drop_all(self.db_engine)


    def create_tables(self):
        table_defs.Base.metadata.create_all(self.db_engine)



if __name__ == '__main__':
    db = DbInit()
    #db.clean_tables()
    db.create_tables()