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
import uuid

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
KEYRING = os.environ["KEYRING"]

sys.path.insert(1, KEYRING)
from pol_app_deepseek   import deepseek_key
from pol_app_openai     import openai_key

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.ERROR)

class TextProcessor:
    def __init__(self, save_json=True):
        self.save_json=save_json
        self.error_count = 0
        self.data_dir = PROJ_ROOT / "data"
        self.default_prompt_fname = PROJ_ROOT / "app/data_collector/prompt.txt"
        self.max_retries = 3    # max retries for json errors
        self.default_deep_model = "deepseek-reasoner"
        self.default_openai_model = "o3-mini"
        with open(self.default_prompt_fname, "r") as f:
            self.default_prompt = f.read()
        return


    def query_ext_model(self, prompt, model_sel):
        client = model_sel["client"]
        model = model_sel["model"]
        
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

        err_path = self.data_dir / f"processing_errs/err_{client}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.txt"
        err_path.parent.mkdir(parents=True, exist_ok=True)
        with open(err_path, "w+") as f:
            f.write(bad_output)
        self.error_count += 1
        return


    def form_data_json(self, serial_json, media_data):
        try:
            result_json = json.loads(serial_json)
            result_json["title"] = media_data["title"]
            result_json["link"] = media_data["link"]
            result_json["filename"] = None
            
            if self.save_json:
                fname = datetime.now().strftime("%Y%m%d_%H%M") + f"__{uuid.uuid4().hex}.json"
                result_json["filename"] = fname
                filepath = self.data_dir / fname
                with open(filepath, "w+") as f:
                    json.dump(result_json, f, indent=2)
            return result_json
        except:
            raise


    def set_up_models(self, deep_client, open_client, model_overrides):
        # default setup
        models = {
            "deepseek": {
                "name"  : "deepseek",
                "client": deep_client,
                "model" : self.default_deep_model
            },
            "openai": {
                "name"  : "openai",
                "client": open_client,
                "model" : self.default_openai_model
            }
        }

        if model_overrides:
            if "deepseek" in model_overrides:
                models["deepseek"]["model"] = model_overrides["deepseek"]
            
            if "openai" in model_overrides:
                models["openai"]["model"] = model_overrides["openai"]
        return models


    def proc(self, media_data, prompt=None, model_overrides=None):
        logger.info(f"Processing - {media_data['link']}")
        deep_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
        openai_client = OpenAI(api_key=openai_key)
        retry_count = 0
        models = self.set_up_models(deep_client, openai_client, model_overrides)
        error = ""

        # Start w/ Deepseek model
        model = models["deepseek"]

        if prompt:
            full_prompt = f"{prompt}\n\nTitle: {media_data['title']}\n\nText:\n{media_data['text']}"
        else:
            full_prompt = f"{self.default_prompt}\n\nTitle: {media_data['title']}\n\nText:\n{media_data['text']}"

        while retry_count < self.max_retries:
            try:
                logger.debug(f"Sending link to AI API - {media_data['link']}")
                result_str = self.query_ext_model(full_prompt, model)
                logger.debug(f"AI API returned result - {media_data['link']}")
            except Exception as e:
                self.save_error(models["name"], f"{e}\n{media_data['link']}\n\n{full_prompt}")
                logger.warning(f"OpenAI error [ {model["name"]}:{model["model"]} ]  error - {e}")
                if model["name"] == "deepseek":
                    model = models["openai"]
                    continue
                else:
                    return (False, media_data['link'])

            # clean json tags that sometime show up
            cleaned_text = re.sub(r'^```json\s*|```$', '', result_str)
            try:
                extract_data = self.form_data_json(cleaned_text, media_data)
                logger.debug(f"Completed processing for - {media_data['link']}")
                return (True, extract_data)
            except json.JSONDecodeError as e:
                retry_count = retry_count + 1
                if retry_count == self.max_retries:
                    error = e
                continue
                    
        #logger.info(f"Finised processing - {media_data['title']}")
        logger.warning(f"Json Decode error: {error}")
        self.save_error(model["name"], f"{e}\n{media_data['link']}\n\n{cleaned_text}")
        return (False, media_data['link'])
