import asyncio
import logging
import sys
import os

# Add backend root to sys.path to allow imports from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.shared.config.settings import settings
import psycopg

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def init_db():
    """
    Initialize the database schema for the application.
    Creates necessary tables if they do not exist.
    """
    conn_str = settings.connection_string
    if not conn_str:
        logger.error("❌ POSTGRES_DB_URI is not set in environment.")
        return

    logger.info(f"Connecting to database...")

    try:
        async with await psycopg.AsyncConnection.connect(conn_str, autocommit=True) as conn:
            async with conn.cursor() as cur:
                logger.info("Checking 'users' table...")
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        uid TEXT PRIMARY KEY,
                        email TEXT,
                        display_name TEXT,
                        photo_url TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_login_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
                logger.info("✅ Table 'users' is ready.")

                logger.info("Checking 'threads' table...")
                
                # Create 'threads' table
                # thread_id: Unique identifier for the conversation
                # owner_uid: Owner user id (Firebase UID)
                # title: Auto-generated title
                # summary: Summary of the conversation
                # created_at: Timestamp of creation
                # updated_at: Timestamp of last update
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS threads (
                        thread_id TEXT PRIMARY KEY,
                        owner_uid TEXT REFERENCES users(uid) ON DELETE CASCADE,
                        title TEXT,
                        summary TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                """)
                await cur.execute("ALTER TABLE threads ADD COLUMN IF NOT EXISTS owner_uid TEXT;")
                await cur.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'threads_owner_uid_fkey'
                        ) THEN
                            ALTER TABLE threads
                            ADD CONSTRAINT threads_owner_uid_fkey
                            FOREIGN KEY (owner_uid) REFERENCES users(uid) ON DELETE CASCADE;
                        END IF;
                    END $$;
                """)
                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_threads_owner_updated_at
                    ON threads(owner_uid, updated_at DESC);
                """)
                logger.info("✅ Table 'threads' is ready.")

                # Verify LangGraph checkpoint tables are managed by AsyncPostgresSaver
                # We don't create them here manually as the checkpointer handles them.
                
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise e

if __name__ == "__main__":
    try:
        asyncio.run(init_db())
        logger.info("🎉 Database initialization completed successfully.")
    except Exception as e:
        logger.error("Initialization script failed.")
        sys.exit(1)
