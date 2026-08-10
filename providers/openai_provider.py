from openai import OpenAI

from config.settings import OPENAI_API_KEY, OPENAI_MODEL
from providers.base_provider import BaseProvider


class OpenAIProvider(BaseProvider):

    def __init__(self):

        if not OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY not found. Please set it in your .env file."
            )

        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def generate(self, prompt: str) -> str:

        response = self.client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
        )

        return response.output_text