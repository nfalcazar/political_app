from dotenv import load_dotenv
import openai as ai
import os
from pathlib import Path
from typing import List

# Load environment variables from .env file relative to this file's location
current_file = Path(__file__)
env_file = current_file.parent.parent / ".env"
load_dotenv(dotenv_path=env_file)

# Get API keys from environment variables
openai_key = os.getenv("OPENAI_KEY")
deepseek_key = os.getenv("DEEP_KEY")

#NOTE: GPT says to avoid global vars if both types of calls used in same file
#TODO: Place AI keys into env
#TODO: determine where to put: cleaned_text = re.sub(r'^```json\s*|```$', '', result_str)

class OpenAiSync:
    def __init__(self, provider="deepseek"):
        self.provider = provider
        self.default_embed_model = "text-embedding-3-small"
        self.default_emded_size = 1536
        try:
            self.client_setup(provider)
        except:
            raise

    
    def client_setup(self, provider):
        if provider == 'deepseek':
            self.client = ai.OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
            self.default_model = "deepseek-chat"
            self.models = [
                "deepseek-chat",
                "deepseek-reasoner"
            ]
        elif provider == "openai":
            self.client = ai.OpenAI(api_key=openai_key)
            self.default_model = "gpt-5"
            self.models = [
            "o3-mini",
            "gpt-4o-mini",
            "gpt-5"
        ]
        else:
            raise ValueError("Unhandled provider passed in.")
        return
    

    def query(self, user_prompt, sys_prompt=None, model=None):
        if not model:
            model = self.default_model

        prompt_list = []
        if sys_prompt:
            prompt_list.append({
                "role": "system",
                "content": sys_prompt
            })
        prompt_list.append({
            "role": "user",
            "content": user_prompt
        })

        try:
            completion = self.client.chat.completions.create(
                model=model,
                messages=prompt_list
            )
            return completion.choices[0].message.content
        except:
            raise


    def get_embedding(self, text: str, model: str = "") -> List[float]:
        """
        Generate embedding for the given text.

        Args:
            text: The input text to generate an embedding for.

        Returns:
            A list of floats representing the embedding.
        """
        text = text.replace("\n", " ")
        if not model:
            model = self.default_embed_model
            
        response = self.client.embeddings.create(
            input=[text],
            model=model,
        ) 
        return response.data[0].embedding


    def get_provider(self):
        '''Return Provider passed during Init (Sanity check)'''
        return self.provider


# class OpenAiAsync:
#     def __init__(self, provider="deepseek"):
#         self.provider = provider
#         self.default_embed_model = "text-embedding-3-small"
#         try:
#             self.client_setup(provider)
#         except:
#             raise

    
#     def client_setup(self, provider):
#         if provider == 'deepseek':
#             self.client = ai.AsyncOpenAI(api_key=getenv("DEEP_KEY"), base_url="https://api.deepseek.com")
#             self.default_model = "deepseek-chat"
#             self.models = [
#                 "deepseek-chat",
#                 "deepseek-reasoner"
#             ]
#         elif provider == "openai":
#             self.client = ai.AsyncOpenAI(api_key=getenv("OPENAI_KEY"))
#             self.default_model = "gpt-4o-mini"
#             self.models = [
#             "o3-mini",
#             "gpt-4o-mini"
#         ]
#         else:
#             raise ValueError("Unhandled provider passed in.")
#         return
    

#     async def query(self, prompt, model=None):
#         if not model:
#             model = self.default_model

#         try:
#             completion = await self.client.chat.completions.create(
#                 model=model,
#                 messages=[{
#                     "role": "user",
#                     "content": prompt
#                 }]
#             )
#             return completion.choices[0].message.content
#         except:
#             raise


#     async def get_embedding(self, text: str, model: str = "") -> List[float]:
#         """
#         Generate embedding for the given text.

#         Args:
#             text: The input text to generate an embedding for.

#         Returns:
#             A list of floats representing the embedding.
#         """
#         text = text.replace("\n", " ")
#         if not model:
#             model = self.default_embed_model

#         response = await self.client.embeddings.create(
#             input=[text],
#             model=model,
#         ) 
#         return response.data[0].embedding


#     def get_provider(self):
#         '''Return Provider passed during Init (Sanity check)'''
#         return self.provider
