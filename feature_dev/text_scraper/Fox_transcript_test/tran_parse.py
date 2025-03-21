with open("./trans_text.txt", "r") as f:
    content = f.readlines()

#print(content)

context_blocks = []
curr_block = {}
curr_block["label"] =  "INTRO"
curr_block["content"] = []

state = "IN_BLOCK"

for line in content:
    if line == '\n':
        continue

    if state == "IN_BLOCK":