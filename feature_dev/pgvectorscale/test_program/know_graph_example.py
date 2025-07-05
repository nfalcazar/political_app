import psycopg2
import pandas as pd
import urllib.parse as urlparse
from config.settings import get_settings
from grab_data import DataGrabber
from sqlalchemy import create_engine

class KnowledgeGraph:
    def __init__(self):
        #self.settings = get_settings()
        #self.db_conn = self.connect_to_db(self.settings.database.service_url)
        self.db_url = "postgresql://postgres:password@localhost:5432/postgres"
        self.sql_engine = create_engine(self.db_url)


    def connect_to_db(self, url):
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
    

    def populate_db(self):
        data_grab = DataGrabber()
        data = data_grab.extract_data_from_fjson()

        # Create Canonical claim table
        canon_claims = data["canonical_claims"]
        cc_df = pd.DataFrame(canon_claims.values())
        cc_df.to_sql(
            name="canonical_claims",
            con=self.sql_engine,
            if_exists='replace',
            index=False
        )

        # Create claim table
        claims = data["claims"]
        claim_df = pd.DataFrame(claims.values())
        claim_df.to_sql(
            name="claims",
            con=self.sql_engine,
            if_exists='replace',
            index=False
        )

        # Create source table
        sources = data["sources"]
        source_df = pd.DataFrame(sources.values())
        source_df.to_sql(
            name="sources",
            con=self.sql_engine,
            if_exists='replace',
            index=False
        )

        # Create events table
        events = data["events"]
        event_df = pd.DataFrame(events.values())
        event_df.to_sql(
            name="events",
            con=self.sql_engine,
            if_exists='replace',
            index=False
        )

        # Create entities table
        entities = data["entities"]
        entity_df = pd.DataFrame(entities.values())
        entity_df.to_sql(
            name="entities",
            con=self.sql_engine,
            if_exists='replace',
            index=False
        )
        return
    

if __name__ == "__main__":
    kgraph = KnowledgeGraph()

    print("Populating DB tables...")
    kgraph.populate_db()
    print("Finished, exiting.")