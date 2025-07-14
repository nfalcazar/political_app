import pandas as pd
import urllib.parse as urlparse
from config.settings import get_settings
from grab_data import DataGrabber
from sqlalchemy import create_engine, select, Column, String
from sqlalchemy.dialects.postgresql import JSON
#from pgai.sqlalchemy import vectorizer_relationship
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from pgvector.sqlalchemy import Vector
from sklearn.metrics.pairwise import cosine_distances
import hdbscan
import matplotlib.pyplot as plt
import numpy as np

from typing import List, Tuple, Any

#import sqlalchemy as sql
from pathlib import Path
import os
from collections import namedtuple
from timescale_vector import client

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])


class Base(DeclarativeBase):
    pass

# class EmbeddingTable(Base):
#     __tablename__ = "embeddings"
#     id = Column("id", String, primary_key=True)
#     metadata_ = Column("metadata", JSON)
#     content = Column("contents")
#     embedding = vectorizer_relationship(dimensions=1536)


class EmbeddingTable(Base):
    __tablename__ = "embeddings"
    id: Mapped[str] = mapped_column(primary_key=True)
    metadata_: Mapped[dict] = mapped_column(JSON)
    contents: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))

class Claim_Cluster():
    def __init__(self):
        self.settings = get_settings()
        self.vector_settings = self.settings.vector_store
        self.db_url = "postgresql://postgres:password@localhost:5432/postgres"
        self.sql_engine = create_engine(self.db_url)
        self.vec_client = client.Sync(
            self.settings.database.service_url,
            self.vector_settings.table_name,
            self.vector_settings.embedding_dimensions,
            time_partition_interval=self.vector_settings.time_partition_interval,
        )


    # def grab_canon_claim_embeds(self):
    #     with self.sql_engine.connect() as conn:
    #         result = conn.execute(select(EmbeddingTable))
    #     return [ dict(id=row.id, text=row.contents, embed=row.embedding ) for row in result]
     

    def grab_embed_list(self):
        with Session(self.sql_engine) as session:
            #result = session.scalars(select(EmbeddingTable.embedding)).all()
            result = session.execute(select(EmbeddingTable.contents, EmbeddingTable.embedding))
        
        return pd.DataFrame(result, columns=["contents", "embedding"])


    def embed_search(self, embedding, limit=15):
        search_args = {"limit": limit,}
        results = self.vec_client.search(embedding, **search_args)
        return self._create_dataframe_from_results(results)
    

    def _create_dataframe_from_results(
        self,
        results: List[Tuple[Any, ...]],
    ) -> pd.DataFrame:
        """
        Create a pandas DataFrame from the search results.

        Args:
            results: A list of tuples containing the search results.

        Returns:
            A pandas DataFrame containing the formatted search results.
        """
        # Convert results to DataFrame
        df = pd.DataFrame(
            results, columns=["id", "metadata", "contents", "embedding", "distance"]
        )

        # Expand metadata column
        df = pd.concat(
            [df.drop(["metadata"], axis=1), df["metadata"].apply(pd.Series)], axis=1
        )

        # Convert id to string for better readability
        df["id"] = df["id"].astype(str)

        return df
    

    def printDBResults(self, results):
        print(f"DB results:")
        for dist, cont in zip(results["distance"], results["contents"]):
            print(f"-  ({dist}) {cont}")
        return
    

    def runClusterAlgo(self, embeddings, algo="hdbscan"):
        cosine_dist = cosine_distances(embeddings)

        if algo == "hdbscan":
            # Run HDBSCAN on the distance matrix
            clusterer = hdbscan.HDBSCAN(metric='precomputed', min_samples=1, min_cluster_size=2)
            labels = clusterer.fit_predict(cosine_dist)
            return labels
        elif algo == "dist_thresh":
            dist_thresh = 0.35
            labels = [-1] * len(embeddings)
            current_label = 0

            for i in range(len(embeddings)):
                if labels[i] == -1:
                    labels[i] = current_label
                    for j in range(i + 1, len(embeddings)):
                        if labels[j] == -1 and cosine_dist[i, j] <= dist_thresh:
                            labels[j] = current_label
                    current_label += 1
            
            return labels
    

    def plotLabels(self, embeddings, labels):
        # Plot
        plt.scatter(embeddings[:, 0], embeddings[:, 1], c=labels, cmap='tab10', s=100)
        plt.title("HDBSCAN Clustering with Cosine Distance")
        plt.xlabel("Embedding dim 1")
        plt.ylabel("Embedding dim 2")
        plt.grid(True)
        plt.show()
        return


if __name__ == "__main__":
    cc = Claim_Cluster()
    claim_embeddings = cc.grab_embed_list()
    embeddings = np.array(claim_embeddings["embedding"].tolist(), dtype=np.float64)
    labels = cc.runClusterAlgo(embeddings, algo="dist_thresh")
    claim_embeddings["cluster_label"] = labels

    grouped_claims = claim_embeddings.groupby("cluster_label")["contents"].apply(list)

    with open('./outputs/clustered_claims.txt', 'w+') as f:
        for label, contents in grouped_claims.items():
            f.write(f"{label}\n---\n")
            for text in contents:
                f.write(f"\t- {text}\n")
            f.write(f"\n\n\n")

