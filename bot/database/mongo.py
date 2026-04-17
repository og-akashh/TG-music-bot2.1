"""
mongo.py — Async MongoDB layer (motor).

Collections:
  • users      — registration, language preference, role
  • chats      — per-group settings, admin list
  • playlists  — user-saved playlists
  • history    — played track history per chat
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import motor.motor_asyncio

from bot.config import config
from bot.utils.logger import get_logger

log = get_logger(__name__)

_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
_db = None


async def connect() -> None:
    global _client, _db
    _client = motor.motor_asyncio.AsyncIOMotorClient(config.DB_URI)
    _db = _client[config.DB_NAME]
    # Ensure indexes
    await _db.users.create_index("user_id", unique=True)
    await _db.chats.create_index("chat_id", unique=True)
    await _db.playlists.create_index([("user_id", 1), ("name", 1)])
    await _db.history.create_index([("chat_id", 1), ("played_at", -1)])
    log.info("MongoDB connected ✓")


async def disconnect() -> None:
    if _client:
        _client.close()
        log.info("MongoDB disconnected")


def _col(name: str):
    if _db is None:
        raise RuntimeError("MongoDB not connected.")
    return _db[name]


# ── User CRUD ─────────────────────────────────────────────────────────────────

async def get_user(user_id: int) -> Optional[Dict]:
    return await _col("users").find_one({"user_id": user_id}, {"_id": 0})


async def upsert_user(user_id: int, data: Dict) -> None:
    data.setdefault("user_id", user_id)
    data.setdefault("created_at", datetime.utcnow())
    data["updated_at"] = datetime.utcnow()
    await _col("users").update_one(
        {"user_id": user_id}, {"$set": data}, upsert=True
    )


async def get_user_lang(user_id: int) -> str:
    doc = await _col("users").find_one({"user_id": user_id}, {"lang": 1})
    return doc.get("lang", config.DEFAULT_LANG) if doc else config.DEFAULT_LANG


async def set_user_lang(user_id: int, lang: str) -> None:
    await upsert_user(user_id, {"lang": lang})


async def get_user_role(user_id: int, chat_id: int) -> str:
    """Returns 'owner' | 'admin' | 'user'"""
    if user_id == config.OWNER_ID:
        return "owner"
    chat = await get_chat(chat_id)
    if chat and user_id in chat.get("admins", []):
        return "admin"
    return "user"


# ── Chat CRUD ─────────────────────────────────────────────────────────────────

async def get_chat(chat_id: int) -> Optional[Dict]:
    return await _col("chats").find_one({"chat_id": chat_id}, {"_id": 0})


async def upsert_chat(chat_id: int, data: Dict) -> None:
    data["updated_at"] = datetime.utcnow()
    await _col("chats").update_one(
        {"chat_id": chat_id}, {"$set": data}, upsert=True
    )


async def add_chat_admin(chat_id: int, user_id: int) -> None:
    await _col("chats").update_one(
        {"chat_id": chat_id},
        {"$addToSet": {"admins": user_id}},
        upsert=True,
    )


async def remove_chat_admin(chat_id: int, user_id: int) -> None:
    await _col("chats").update_one(
        {"chat_id": chat_id},
        {"$pull": {"admins": user_id}},
    )


async def get_chat_setting(chat_id: int, key: str, default: Any = None) -> Any:
    doc = await get_chat(chat_id)
    return doc.get("settings", {}).get(key, default) if doc else default


async def set_chat_setting(chat_id: int, key: str, value: Any) -> None:
    await _col("chats").update_one(
        {"chat_id": chat_id},
        {"$set": {f"settings.{key}": value}},
        upsert=True,
    )


# ── Playlist CRUD ─────────────────────────────────────────────────────────────

async def save_playlist(user_id: int, name: str, tracks: List[Dict]) -> None:
    await _col("playlists").update_one(
        {"user_id": user_id, "name": name},
        {"$set": {"tracks": tracks, "updated_at": datetime.utcnow()}},
        upsert=True,
    )


async def get_playlist(user_id: int, name: str) -> Optional[Dict]:
    return await _col("playlists").find_one(
        {"user_id": user_id, "name": name}, {"_id": 0}
    )


async def list_playlists(user_id: int) -> List[str]:
    cursor = _col("playlists").find({"user_id": user_id}, {"name": 1})
    return [doc["name"] async for doc in cursor]


async def delete_playlist(user_id: int, name: str) -> bool:
    result = await _col("playlists").delete_one({"user_id": user_id, "name": name})
    return result.deleted_count > 0


# ── Play History ──────────────────────────────────────────────────────────────

async def add_history(chat_id: int, track: Dict) -> None:
    await _col("history").insert_one(
        {"chat_id": chat_id, "track": track, "played_at": datetime.utcnow()}
    )


async def get_history(chat_id: int, limit: int = 10) -> List[Dict]:
    cursor = (
        _col("history")
        .find({"chat_id": chat_id}, {"_id": 0, "track": 1, "played_at": 1})
        .sort("played_at", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


# ── Stats ─────────────────────────────────────────────────────────────────────

async def get_stats() -> Dict:
    return {
        "users": await _col("users").count_documents({}),
        "chats": await _col("chats").count_documents({}),
        "playlists": await _col("playlists").count_documents({}),
        "history_entries": await _col("history").count_documents({}),
    }
