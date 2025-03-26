# TODO: Webscrape of sources in file to try and grab weblinks to sources
# TODO: Add sorts in textprocessor to simplify data processing logic
#       ie: make sure all lists are in order of their id's
# TODO: Add uid, emded_id fields to elements stored in textprocessor to allow modification by hand

import json
import os
from pathlib import Path

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
data_dir = PROJ_ROOT / "data"

data_files = []
for root, dirs, files in os.walk(data_dir):
    for file in files:
        if file.lower().endswith('.json'):
            data_files.append(os.path.join(root, file))

# for file in data_files:
#     print(file)

claims_text = []
claims = []
categories = set()

# sources = []
# events = []
# entities = []
# event_unames = set()
# source_names = set()
# entity_names = set()

sources = {}
events = {}
entities = {}

claim_count = 0
event_count = 0
source_count = 0
entity_count = 0

for file in data_files:
    try:
        with open(file, "r") as f:
            data_json = json.load(f)
    except Exception as e:
        print(e)

    # Metadata to attach to any elements grabbed from media
    link = data_json["link"]
    if "filename" in data_json:
        filename = data_json["filename"]
    else:
        filename = os.path.basename(file)

    # Update element lists, wait to update claims list until end
    for event in data_json["events"]:
        event_uname = f"{event['name']} {event['date']}"
        if event_uname not in events.keys():
            event["uname"] = event_uname
            event["uid"] = event_count
            event_count += 1
            events[event_uname] = event
        else:
            event["uid"] = events[event_uname]["uid"]

    for source in data_json["sources"]:
        if source["name"] not in sources.keys():
            source['uid'] = source_count
            source_count += 1
            sources[source["name"]] = source
        else:
            source['uid'] = sources[source["name"]]["uid"]

    for entity in data_json["entities"]:
        if entity["name"] not in entities.keys():
            entity['uid'] = entity_count
            entity_count += 1
            entities[entity["name"]] = entity
        else:
            entity['uid'] = entities[entity["name"]]["uid"]

    for claim in data_json["claims"]:
        claim["source_filename"] = filename
        claim["source_weblink"] = link
        claim["embed_id"] = None
        claim["uid"] = claim_count
        claim_count = claim_count + 1

        #claims.append(claim)

        if "categories" in claim:
            for category in claim["categories"]:
                categories.add(category)
            cat_str = " ".join(claim["categories"])
        elif "category" in claim:
            categories.add(claim["category"])
            cat_str = claim["category"]

        # String for txtai embedding training ( text + categories )
        train_text = claim["text"] + " : " + cat_str
        claim["train_text"] = train_text
        claims_text.append(train_text)

    # run to correct ref pointers
    # Going to assume json won't always list elements in order of their ids
    for claim in data_json["claims"]:
        #print(f"\n\n\n{claim}\n")
        for entity in data_json["entities"]:
            if entity["id"] == claim["speaker"]:
                claim["speaker"] = entity["uid"]
                break
        
        for i in range(len(claim["sources"])):
            source_id = claim["sources"][i]
            for source in data_json["sources"]:
                if source["id"] == source_id:
                    claim["sources"][i] = source["uid"]
                    break

        for i in range(len(claim["events"])):
            event_id = claim["events"][i]
            for event in data_json["events"]:
                if event["id"] == event_id:
                    claim["events"][i] = event["uid"]
                    break

        #print(f"{claim['counter_arguments']} size: {len(claim['counter_arguments'])}")
        for i in range(len(claim["counter_arguments"])):
            #print(f"\tcounterargs - {i}:")
            counter_argument_id = claim["counter_arguments"][i]
            for counter_claim in data_json["claims"]:
                if counter_claim["id"] == counter_argument_id:
                    claim["counter_arguments"][i] = counter_claim["uid"]
                    break
        
        #print(f"\n{claim}\n")

    # Add updated claims to store of claims
    for claim in data_json["claims"]:
        claims.append(claim)


# Output results in separate json files
with open("./outputs/claims.json", "w+") as f:
    obj_json = {}
    obj_json["claim_texts"] = claims_text
    obj_json["claim_categories"] = list(categories)
    obj_json["claims"] = claims
    json.dump(obj_json, f, indent=2)

with open("./outputs/sources.json", "w+") as f:
    obj_json = {}
    obj_json["source_names"] = list(sources.keys())
    obj_json["sources"] = list(sources.values())
    json.dump(obj_json, f, indent=2)

with open("./outputs/entities.json", "w+") as f:
    obj_json = {}
    obj_json["entity_names"] = list(entities.keys())
    obj_json["entities"] = list(entities.values())
    json.dump(obj_json, f, indent=2)

with open("./outputs/events.json", "w+") as f:
    obj_json = {}
    obj_json["event_unames"] = list(events.keys())
    obj_json["events"] = list(events.values())
    json.dump(obj_json, f, indent=2)



'''
# Old method of using sets and lists, issues when existing elements hit again:
# sources = []
# events = []
# entities = []
# event_unames = set()
# source_names = set()
# entity_names = set()

for file in data_files:
    try:
        with open(file, "r") as f:
            data_json = json.load(f)
    except Exception as e:
        print(e)

    # Metadata to attach to any elements grabbed from media
    link = data_json["link"]
    if "filename" in data_json:
        filename = data_json["filename"]
    else:
        filename = os.path.basename(file)

    # Update element lists, wait to update claims list until end
    for event in data_json["events"]:
        event_uname = f"{event['name']} {event['date']}"
        if event_uname not in event_unames:
            event_unames.add(event_uname)
            event["uid"] = event_count
            event_count += 1
            events.append(event)

    for source in data_json["sources"]:
        if source["name"] not in source_names:
            source_names.add(source["name"])
            source['uid'] = source_count
            source_count += 1
            sources.append(source)

    for entity in data_json["entities"]:
        if entity["name"] not in entity_names:
            entity_names.add(entity["name"])
            entity['uid'] = entity_count
            entity_count += 1
            entities.append(entity)
        else:
            entity['uid'] = 

    for claim in data_json["claims"]:
        claim["source_filename"] = filename
        claim["source_weblink"] = link
        claim["embed_id"] = None
        claim["uid"] = claim_count
        claim_count = claim_count + 1

        #claims.append(claim)
        claims_text.append(claim["text"])

        if "categories" in claim:
            for category in claim["categories"]:
                categories.add(category)
        elif "category" in claim:
            categories.add(claim["category"])

    # run to correct ref pointers
    # Going to assume json won't always list elements in order of their ids
    for claim in data_json["claims"]:
        print(f"\n\n\n{claim}\n")
        for entity in data_json["entities"]:
            if entity["id"] == claim["speaker"]:
                claim["speaker"] = entity["uid"]
                break
        
        for i in range(len(claim["sources"])):
            source_id = claim["sources"][i]
            for source in data_json["sources"]:
                if source["id"] == source_id:
                    claim["sources"][i] = source["uid"]
                    break

        for i in range(len(claim["events"])):
            event_id = claim["events"][i]
            for event in data_json["events"]:
                if event["id"] == event_id:
                    claim["events"][i] = event["uid"]
                    break

        print(f"{claim['counter_arguments']} size: {len(claim['counter_arguments'])}")
        for i in range(len(claim["counter_arguments"])):
            print(f"\tcounterargs - {i}:")
            counter_argument_id = claim["counter_arguments"][i]
            for counter_claim in data_json["claims"]:
                if counter_claim["id"] == counter_argument_id:
                    claim["counter_arguments"][i] = counter_claim["uid"]
                    break
        
        print(f"\n{claim}\n")

    # Add updated claims to store of claims
    for claim in data_json["claims"]:
        claims.append(claim)

'''