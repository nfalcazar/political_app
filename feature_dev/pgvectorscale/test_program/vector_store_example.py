# vector insert imports
from datetime import datetime
import pandas as pd
from database.vector_store import VectorStore
from timescale_vector.client import uuid_from_time

# Similarity search imports
#from datetime import datetime
#from database.vector_store import VectorStore
from services.synthesizer import Synthesizer
from timescale_vector import client

from grab_data import DataGrabber

# TODO: Look to parallelize embedding gen?

def main():
    vec = VectorStore()

    # Set up DB
    # data_grab = DataGrabber()
    # print("Grabbing data from stored files...")
    # canon_claims = data_grab.extract_data_from_fjson()["canonical_claims"]
    # data_rows = []
    # print("Getting Embeddings from OpenAI...")
    # for cclaim in canon_claims.values():
    #     content = cclaim["text"]
    #     embedding = vec.get_embedding(content)
    #     entry = {
    #         "id": str(uuid_from_time(datetime.now())),
    #         "metadata": {
    #             "data_id": cclaim["id"],
    #             "category": cclaim["category"]
    #         },
    #         "content": content,
    #         "embedding": embedding
    #     }
    #     data_rows.append(entry)
    #     print(f"\t- {content}")

    # print("\n\nCreating PD Dataframe from grabbed data")
    # df = pd.DataFrame(data_rows)
    # print("Creating DB tables...")
    # vec.create_tables()
    # print("Adding DataFrame to DB...")
    # vec.upsert(df)

    print("Finished setup, entering input loop.\n")
    # Question loop w/ similarity search
    query = None
    while query != "exit":
        query = input("Query (\"exit\" to quit):  ")
        if query == "exit":
            continue

        results = vec.search(query, limit=10)
        response = Synthesizer.generate_response(question=query, context=results)

        print(f"DB results:")
        for row in results["content"]:
            print(f"-  {row}")

        print(f"\n\nAnswer:\n{response.answer}\n")
        print("Thought process:")
        for thought in response.thought_process:
            print(f"- {thought}")
        print(f"\nContext: {response.enough_context}")


if __name__ == "__main__":
    main()