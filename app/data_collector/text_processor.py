# TODO: Should I move queue json structure into own class each file can refernce?
# TODO: Test if adding a summary before full text helps AI w/ processing

from openai import OpenAI
from multiprocessing import Queue
import re
import sys
from datetime import datetime
from pathlib import Path
import json
import logging
import os
from pathlib import Path

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
KEYRING = os.environ["KEYRING"]

sys.path.insert(1, KEYRING)
from pol_app_deepseek   import deepseek_key
from pol_app_openai     import openai_key

logger = logging.getLogger(__name__)

class TextProcessor:
    def __init__(self, save_json=True):
        self.save_json=save_json
        self.error_count = 0
        self.data_dir = PROJ_ROOT / "data"
        self.deep_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
        self.openai_client = OpenAI(api_key=openai_key)
        self.default_prompt_fname = PROJ_ROOT / "app/data_collector/prompt.txt"
        self.max_retries = 3    # max retries for json errors
        with open(self.default_prompt_fname, "r") as f:
            self.default_prompt = f.read()
        return


    def query_ext_model(self, prompt, client, model=None):
        if client == "deepseek":
            client = self.deep_client
            if not model:
                model = "deepseek-reasoner"
        elif client == "openai":
            client = self.openai_client
            if not model:
                model = "o3-mini"
        
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            return completion.choices[0].message.content
        except:
            raise
        return
    

    def save_error(self, client, bad_output):
        if not self.save_json:
            return

        err_path = self.data_dir / f"processing_errs/err_{client}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        err_path.parent.mkdir(parents=True, exist_ok=True)
        with open(err_path, "w+") as f:
            f.write(bad_output)
        self.error_count += 1
        return
    

    def form_data_json(self, serial_json, media_data):
        try:
            # form result json
            time_str = datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
            filepath = self.data_dir / time_str

            result_json = json.loads(serial_json)
            result_json["title"] = media_data["title"]
            result_json["link"] = media_data["link"]
            result_json["filename"] = time_str
            
            if self.save_json:
                with open(filepath, "w+") as f:
                    json.dump(result_json, f, indent=2)
            return result_json
        except:
            raise
           

    def proc(self, media_data, prompt=None):
        logger.info(f"Processing - {media_data['title']}")
        retry_count = 0
        client_name = "deepseek"

        if prompt:
            full_prompt = f"{prompt}\n\nTitle: {media_data['title']}\n\nText:\n{media_data['text']}"
        else:
            full_prompt = f"{self.default_prompt}\n\nTitle: {media_data['title']}\n\nText:\n{media_data['text']}"

        while retry_count < self.max_retries:
            try:
                result_str = self.query_ext_model(full_prompt, client_name)
            except Exception as e:
                self.save_error(client_name, f"{e}\n{media_data['link']}\n\nfull_prompt")
                logger.warning(f"OpenAI error. Client - {client_name}  error - {e}")
                if client_name == "deepseek":
                    client_name = "openai"
                    continue
                else:
                    return False

            # clean json tags that sometime show up
            cleaned_text = re.sub(r'^```json\s*|```$', '', result_str)
            try:
                extract_data = self.form_data_json(cleaned_text, media_data)
            except json.JSONDecodeError as e:
                retry_count = retry_count + 1
                if retry_count == self.max_retries:
                    self.save_error(client_name, f"{e}\n{media_data['link']}\n\n{cleaned_text}")
                    logger.warning(f"{e} - Error output saved to data/processing_errs")

            return extract_data

        #logger.info(f"Finised processing - {media_data['title']}")
        return False
