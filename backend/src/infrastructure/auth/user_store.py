import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_USER_TABLE_READY = False
_USER_TABLE_LOCK = asyncio.Lock()


async def _ensure_user_table(pool) -> None:
    global _USER_TABLE_READY
    if _USER_TABLE_READY:
        return
    async with _USER_TABLE_LOCK:
        if _USER_TABLE_READY:
            return
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        uid TEXT PRIMARY KEY,
                        email TEXT,
                        display_name TEXT,
                        photo_url TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_login_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
                await conn.commit()
        _USER_TABLE_READY = True


async def upsert_user(pool, decoded: dict[str, Any]) -> None:
    if pool is None:
        raise RuntimeError("Postgres pool is not initialized.")

    uid = decoded.get("uid") or decoded.get("user_id") or decoded.get("sub")
    if not uid:
        raise ValueError("Firebase token missing uid.")

    email = decoded.get("email")
    display_name = decoded.get("name") or decoded.get("displayName")
    photo_url = decoded.get("picture")

    await _ensure_user_table(pool)

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO users (uid, email, display_name, photo_url)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (uid) DO UPDATE
                SET email = EXCLUDED.email,
                    display_name = EXCLUDED.display_name,
                    photo_url = EXCLUDED.photo_url,
                    last_login_at = NOW();
                """,
                (uid, email, display_name, photo_url),
            )
            await conn.commit()
