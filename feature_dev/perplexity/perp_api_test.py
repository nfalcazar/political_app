import requests
import sys
import os
from pathlib import Path
import json

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
KEYRING = os.environ["KEYRING"]
sys.path.insert(1, KEYRING)
from pol_app_perplexity import perplexity_key

# Set up the API endpoint and headers
url = "https://api.perplexity.ai/chat/completions"
headers = {
    "Authorization": f"Bearer {perplexity_key}",  # Replace with your actual API key
    "Content-Type": "application/json"
}

# Define the request payload
payload = {
    #"model": "sonar-pro",      # Complex search model
    "model": "sonar",           # Gen use search model
    "messages": [
        {"role": "user", "content": "What was the title and contents of the first bill passed in California in 2025?"}
    ]
}

# Make the API call
response = requests.post(url, headers=headers, json=payload)

# Print the AI's response
print(response.json())

with open("./outputs/perp_api_resp.json", "w+") as f:
    json.dump(response.json(), f, indent=2)