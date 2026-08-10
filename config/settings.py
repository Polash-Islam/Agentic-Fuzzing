import os
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# LLM Configuration
# -----------------------------

LLM_PROVIDER = "openai"

OPENAI_MODEL = "gpt-5.5"

# Future Providers
GEMINI_MODEL = "gemini-2.0-flash"
CLAUDE_MODEL = "claude-sonnet-4"

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# Agent Settings
MAX_ITERATIONS = 5
MAX_EXAMPLES = 500
TIMEOUT = 5