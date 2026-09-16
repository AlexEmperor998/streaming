from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

class Database:
    def __init__(self):
        self.client = None
        self.links = None

    async def connect(self):
        self.client = AsyncIOMotorClient(Config.MONGODB_URL, serverSelectionTimeoutMS=10000)
        await self.client.admin.command("ping")
        self.links = self.client[Config.DB_NAME]["links"]
        await self.links.create_index("message_id")

    async def close(self):
        if self.client:
            self.client.close()

    async def save_link(self, unique_id, message_id, file_id, file_name, mime_type, file_size):
        await self.links.update_one(
            {"_id": unique_id},
            {"$set": {
                "message_id": message_id,
                "file_id": file_id,
                "file_name": file_name or "file",
                "mime_type": mime_type or "application/octet-stream",
                "file_size": int(file_size or 0),
            }},
            upsert=True,
        )

    async def get_link(self, unique_id):
        return await self.links.find_one({"_id": unique_id})

    async def delete_link(self, unique_id):
        await self.links.delete_one({"_id": unique_id})

db = Database()
