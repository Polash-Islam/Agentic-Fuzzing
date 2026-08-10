from google import genai

from config.settings import GEMINI_API_KEY, GEMINI_MODEL
from providers.base_provider import BaseProvider


class GeminiProvider(BaseProvider):
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def generate(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        return response.text