import psycopg2
import pandas as pd
import urllib.parse as urlparse
from settings import get_settings

class SqlStore:
    def __init__(self):
        self.settings= get_settings()
        self.db_url = self.settings.database.service_url
        self.db_conn = self._connect_to_db(self.db_url)


    def _connect_to_db(self, url):
        # Parse the URL
        result = urlparse.urlparse(url)
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port

        # Connect
        conn = psycopg2.connect(
            dbname=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        return conn
    

    def create_table(self, table_name, data, overwrite=False):
        pass