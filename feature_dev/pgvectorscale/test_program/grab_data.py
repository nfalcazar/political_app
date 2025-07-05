import hashlib
import json
import os
from pathlib import Path

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
data_dir = PROJ_ROOT / "data"

class DataGrabber:
    def __init__(self):
        pass


    def generate_id(self, text: str) -> str:
        """Generate a stable unique ID from a text string."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    

    def extract_data_from_fjson(self, data_dir=data_dir, save_json=False):
        json_flist = []
        for filename in os.listdir(data_dir):
            if filename.lower().endswith('.json'):
                filepath = os.path.join(data_dir, filename)
                if os.path.isfile(filepath):
                    json_flist.append(filepath)

        # Init containers
        events_by_id = {}
        sources_by_id = {}
        entities_by_id = {}
        claims_by_id = {}
        canonical_by_id = {}

        # Grab data from files
        for file in json_flist:
            with open(file, "r") as f:
                data = json.load(f)

            # 1. Group events
            local_event_id_to_hash = {}
            for event in data.get('events', []):
                orig_id = event['id']
                event['uname'] = f"{event['name']} {event['date']}"
                new_id = self.generate_id(event['uname'])
                event['id'] = new_id
                local_event_id_to_hash[orig_id] = new_id
                if new_id not in events_by_id.keys():
                    events_by_id[new_id] = event
                    
            # 2. Group sources
            local_source_id_to_hash = {}
            for source in data.get('sources', []):
                orig_id = source['id']
                new_id = self.generate_id(source['name'])
                source['id'] = new_id
                local_source_id_to_hash[orig_id] = new_id
                if new_id not in sources_by_id.keys():
                    sources_by_id[new_id] = source
                    
            # 3. Group entities
            local_entity_id_to_hash = {}
            for entity in data.get('entities', []):
                orig_id = entity['id']
                try:
                    entity['uname'] = f"{entity['name']} {entity['title']}"
                except KeyError:
                    # If entity is org, AI might leave out title, seems happen rarely
                    entity['uname'] = entity["name"]
                new_id = self.generate_id(entity['uname'])
                entity['id'] = new_id
                local_entity_id_to_hash[orig_id] = new_id
                if new_id not in entities_by_id.keys():
                    entities_by_id[new_id] = entity
                    
            # 3. First run of canonical claims to generate ID's
            local_canon_id_to_hash = {}
            for cc in data.get('canonical_claims', []):
                orig_id = cc['id']
                new_id = self.generate_id(cc['text'])
                cc['id'] = new_id
                local_canon_id_to_hash[orig_id] = new_id

            # 3. Group claims
            local_claim_id_to_hash = {}
            for claim in data.get('claims', []):
                orig_id = claim['id']
                new_id = self.generate_id(claim['text'])
                claim['id'] = new_id
                # Replace event, source, canoncial, and entity references with hashed IDs
                claim['events'] = [
                    local_event_id_to_hash.get(e, e) for e in claim.get('events', [])
                ]
                claim['sources'] = [
                    local_source_id_to_hash.get(s, s) for s in claim.get('sources', [])
                ]
                claim['canonical_id'] = local_canon_id_to_hash.get(claim['canonical_id'], '')
                # Missing speaker only happened in one file so far. Might not be major issue
                try:
                    claim['speaker'] = local_entity_id_to_hash.get(claim['speaker'], '')
                except KeyError:
                    print(f"Claim missing speaker in file: {data.get('filename', '')}")
                    claim["speaker"] = ''
                local_claim_id_to_hash[orig_id] = new_id
                claim['link'] = data.get('link', '')
                claim['file'] = data.get('filename', '')
                claims_by_id[new_id] = claim

            # 4. Group canonical claims with updated refs
            for cc in data.get('canonical_claims', []):
                # Map any claim_id or claim_ids fields to new hashed claim IDs
                try:
                    cc['supporting_claims'] = [
                        local_claim_id_to_hash.get(cid, cid) for cid in cc['supporting_claims']
                    ]
                    cc['refuting_claims'] = [
                        local_claim_id_to_hash.get(cid, cid) for cid in cc['refuting_claims']
                    ]
                    cc['uncertain_claims'] = [
                        local_claim_id_to_hash.get(cid, cid) for cid in cc['uncertain_claims']
                    ]
                except KeyError as e:
                    print(f"{e}. Malformed dict for file: {data.get('filename')}")

                canonical_by_id[new_id] = cc

        result_json = {
            "canonical_claims": canonical_by_id,
            "claims": claims_by_id,
            "sources": sources_by_id,
            "events": events_by_id,
            "entities": entities_by_id
        }

        if save_json:
            with open("./outputs/canon_claim.json", "w+") as data_file:
                json.dump(result_json, data_file, indent=2)

        return result_json
    

if __name__ == "__main__":
    dgrab = DataGrabber()
    dgrab.extract_data_from_fjson(save_json=True)