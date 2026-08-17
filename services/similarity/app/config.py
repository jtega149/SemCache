import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY")
    redis_url: str = os.getenv("REDIS_URL")
    similarity_threshold: str = os.getenv("SIMILARITY_THRESHOLD")
    default_ttl_seconds: int = int(os.getenv("DEFAULT_TTL_SECONDS", "86400"))
    embedding_model: str = os.getenv("EMBEDDING_MODEL")

settings = Settings()