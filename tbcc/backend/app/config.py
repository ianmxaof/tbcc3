import os


def get_settings():
    return {
        "database_url": os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost/tbcc"),
        "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        "api_id": os.getenv("API_ID"),
        "api_hash": os.getenv("API_HASH"),
        "admin_telegram_id": os.getenv("ADMIN_TELEGRAM_ID"),
    }
