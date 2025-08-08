import openai as ai
from os import getenv
from typing import List

#NOTE: GPT says to avoid global vars if both types of calls used in same file
#TODO: Place AI keys into env
#TODO: determine where to put: cleaned_text = re.sub(r'^```json\s*|```$', '', result_str)

class OpenAiAsync:
    def __init__(self, provider="deepseek"):
        self.provider = provider
        self.default_embed_model = "text-embedding-3-small"
        try:
            self.client_setup(provider)
        except:
            raise

    
    def client_setup(self, provider):
        if provider == 'deepseek':
            self.client = ai.AsyncOpenAI(api_key=getenv("DEEP_KEY"), base_url="https://api.deepseek.com")
            self.default_model = "deepseek-chat"
            self.models = [
                "deepseek-chat",
                "deepseek-reasoner"
            ]
        elif provider == "openai":
            self.client = ai.AsyncOpenAI(api_key=getenv("OPENAI_KEY"))
            self.default_model = "gpt-4o-mini"
            self.models = [
            "o3-mini",
            "gpt-4o-mini"
        ]
        else:
            raise ValueError("Unhandled provider passed in.")
        return
    

    async def query(self, prompt, model=None):
        if not model:
            model = self.default_model

        try:
            completion = await self.client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            return completion.choices[0].message.content
        except:
            raise


    async def get_embedding(self, text: str, model: str = "") -> List[float]:
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

        response = await self.client.embeddings.create(
            input=[text],
            model=model,
        ) 
        return response.data[0].embedding


    def get_provider(self):
        '''Return Provider passed during Init (Sanity check)'''
        return self.provider



class OpenAiSync:
    def __init__(self, provider="deepseek"):
        self.provider = provider
        self.default_embed_model = "text-embedding-3-small"
        try:
            self.client_setup(provider)
        except:
            raise

    
    def client_setup(self, provider):
        if provider == 'deepseek':
            self.client = ai.OpenAI(api_key=getenv("DEEP_KEY"), base_url="https://api.deepseek.com")
            self.default_model = "deepseek-chat"
            self.models = [
                "deepseek-chat",
                "deepseek-reasoner"
            ]
        elif provider == "openai":
            self.client = ai.OpenAI(api_key=getenv("OPENAI_KEY"))
            self.default_model = "gpt-4o-mini"
            self.models = [
            "o3-mini",
            "gpt-4o-mini"
        ]
        else:
            raise ValueError("Unhandled provider passed in.")
        return
    

    def query(self, prompt, model=None):
        if not model:
            model = self.default_model

        try:
            completion = self.client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
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