from dotenv import load_dotenv
from os import getenv
import psycopg2
import pandas as pd
import urllib.parse as urlparse
from sqlalchemy import create_engine, inspect
from timescale_vector import client

from .table_defs import Base
from .vector_api import VectorStore
from .sql_api import SqlStore

load_dotenv(dotenv_path="../.env")


class DbInit:
    def __init__(self):
        self.claim_store = VectorStore(table_name="canon_claims")
        self.fact_store = VectorStore(table_name="facts")
        self.sql_store = SqlStore()
        self.db_engine = create_engine(getenv("SQL_URL"))
        self.create_tables()

    # TODO: Doesn't seem to work, look into it
    # def clean_tables(self):
    #     Base.metadata.drop_all(self.db_engine)


    def create_tables(self):
        self.claim_store.create_tables()
        self.fact_store.create_tables()
        Base.metadata.create_all(self.db_engine)


if __name__ == '__main__':
    db = DbInit()
    #db.clean_tables()

    # input("Remove all tables? (y/n)")
    # if input() == "y":
    #     db.clean_tables()