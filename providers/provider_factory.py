from config.settings import LLM_PROVIDER

from providers.openai_provider import OpenAIProvider
from providers.gemini_provider import GeminiProvider


class ProviderFactory:

    @staticmethod
    def get_provider():

        provider = LLM_PROVIDER.lower()

        if provider == "openai":
            return OpenAIProvider()

        elif provider == "gemini":
            return GeminiProvider()

        raise ValueError(f"Unknown provider: {provider}")