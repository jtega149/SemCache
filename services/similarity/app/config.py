import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY")
    redis_url: str = os.getenv("REDIS_URL")
    similarity_threshold: str = os.getenv("SIMILARITY_THRESHOLD", "0.95")
    threshold_loose: str = os.getenv("THRESHOLD_LOOSE", "0.90")
    threshold_strict: str = os.getenv("THRESHOLD_STRICT", "0.98")
    default_ttl_seconds: int = int(os.getenv("DEFAULT_TTL_SECONDS", "86400"))
    embedding_model: str = os.getenv("EMBEDDING_MODEL")

settings = Settings()