#   FROM GITHUB DOCS:
#   Hybrid search can be expensive, might have issue with scaling requests

from txtai.embeddings import Embeddings
import json
import os
from pathlib import Path
import pprint

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
data_file = PROJ_ROOT / "feature_dev/data_processor/outputs/canon_claim.json"

with open(data_file, "r") as f:
    claim_data = json.load(f)

canonical_claims = claim_data["canonical_claims"].values()
claims = claim_data["claims"]
# etc...

hybrid_thresh = 0.9  # 0 - sparse(keywords) to 1 - dense(semantic)
sim_thresh = 0.7237
embeddings = Embeddings(hybrid=True, content=True)

claim_cnt = 0
for canon_claim in canonical_claims:
    hit = embeddings.search(canon_claim['text'], limit=1, weights=hybrid_thresh)
    if hit and hit[0]['score'] > sim_thresh:
        print(f"Found dup claim: sim_score - {hit[0]['score']}")
        print(f"query : {canon_claim['text']}")
        print(f"result: {hit[0]['text']}\n")
    else:
        embeddings.upsert([(canon_claim['id'], canon_claim['text'])])
        claim_cnt += 1

print("\n\n")
while True:
    bad_value = False
    user_input = input("Enter threshold between: 0 - keyword, 1 - semantic\n")
    try:
        thresh = float(user_input)
    except:
        bad_value = True

    if bad_value or thresh < 0 or thresh > 1:
        print("\tBad value for theshold passed, need value between 0 - 1\n")
        continue

    print(f"Using threshold of {thresh}.\n")
    user_input = input("Enter claim query:\n")

    print("\n\nTop 3 Results:\n")
    for result in embeddings.search(user_input, limit=3, weights=thresh):
        pprint.pp(result, indent=4, width=120)