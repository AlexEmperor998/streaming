import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    OWNER_ID = int(os.getenv("OWNER_ID", "0"))
    STORAGE_CHANNEL_ID = os.getenv("STORAGE_CHANNEL_ID", "")
    FORCE_SUB_CHANNEL_ID = os.getenv("FORCE_SUB_CHANNEL_ID", "")
    FORCE_SUB_CHANNEL_USERNAME = os.getenv("FORCE_SUB_CHANNEL_USERNAME", "").lstrip("@")
    BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
    MONGODB_URL = os.getenv("MONGODB_URL", "")
    DB_NAME = os.getenv("DB_NAME", "StreamLinksDB")
    PORT = int(os.getenv("PORT", "8000"))

    @classmethod
    def validate(cls):
        missing = []
        for name, value in {
            "BOT_TOKEN": cls.BOT_TOKEN,
            "OWNER_ID": cls.OWNER_ID,
            "STORAGE_CHANNEL_ID": cls.STORAGE_CHANNEL_ID,
            "BASE_URL": cls.BASE_URL,
            "MONGODB_URL": cls.MONGODB_URL,
        }.items():
            if not value:
                missing.append(name)
        if missing:
            raise RuntimeError("Missing environment variables: " + ", ".join(missing))
