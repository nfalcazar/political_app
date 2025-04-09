from txtai.embeddings import Embeddings
import os
from pathlib import Path
import json
import pprint


# import matplotlib
# matplotlib.use('qtagg')
import matplotlib.pyplot as plt
import networkx as nx

# Grab data from result of feature_dev/data_processor
PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
data_file = PROJ_ROOT/ "feature_dev/data_processor/outputs/claims.json"

with open(data_file, "r") as f:
    claims = json.load(f)

embeddings = Embeddings({
    #"path": "sentence-transformers/all-MiniLM-L6-v2",
    "path": "sentence-transformers/paraphrase-MiniLM-L3-v2",
    "content": True,
    "functions": [
        {"name": "graph", "function": "graph.attribute"},
    ],
    "expressions": [
        {"name": "category", "expression": "graph(indexid, 'category')"},
        {"name": "topic", "expression": "graph(indexid, 'topic')"},
        {"name": "topicrank", "expression": "graph(indexid, 'topicrank')"}
    ],
    "graph": {
        "limit": 5,
        "minscore": 0.1,
        "topics": {
            "categories": claims["claim_categories"]
        }
    }
})

embeddings.index((x, text, None) for x, text in enumerate(claims["claim_texts"]))
graph = embeddings.graph
print()
print(len(embeddings.graph.topics))
print(list(graph.topics.keys())[:5])
print()
top_topic = list(graph.topics.keys())[1]
print(top_topic)
print(embeddings.search(f"select text from txtai where topic = '{top_topic}' and topicrank = 0", 1)[0]["text"])
print()
print()

for x, topic in enumerate(list(graph.topics.keys())[:5]):
    print(graph.categories[x], topic)
     
# Plot graph
# labels = {x: f"{graph.attribute(x, 'id')} ({x})" for x in graph.scan()}
# options = {
#     "node_size": 750,
#     "node_color": "#0277bd",
#     "edge_color": "#454545",
#     "font_color": "#fff",
#     "font_size": 6,
#     "alpha": 1.0
# }

# fig, ax = plt.subplots(figsize=(17, 8))
# pos = nx.spring_layout(graph.backend, seed=0, k=0.9, iterations=50)
# nx.draw_networkx(graph.backend, pos=pos, labels=labels, **options)
# ax.set_facecolor("#303030")
# ax.axis("off")
# fig.set_facecolor("#303030")

#plt.show()
#plt.savefig("./graph.png")
print()
print()

# for x in graph.showpath(50, 100):
#     print(graph.node(x))

# print()
# print()
# query = "Are immigrants causing crime"
# print(f"query: {query}")
# #print([(result["score"], result["text"]) for result in embeddings.search(query, limit=50)])
# for result in embeddings.search(query, limit=10):
#     pprint.pp(result, indent=4, width=120)
#     print()

# print()
# print()

# query = "Can you tell me about Tren de Aragua"
# print(f"query: {query}")
# for result in embeddings.search(query, limit=10):
#     pprint.pp(result, indent=4, width=120)
#     print()

print()
print()

query = "Who is against deporting illegal immigrants"
print(f"query: {query}")
for result in embeddings.search(query, limit=10):
    pprint.pp(result, indent=4, width=120)
    print()

while True:
    user_input = input("Enter graph query, or 'quit' to exit.\n")
    if user_input.lower() == "quit":
        break

    query = user_input
    for result in embeddings.search(query, limit=10):
        pprint.pp(result, indent=4, width=120)
        print()
    print()