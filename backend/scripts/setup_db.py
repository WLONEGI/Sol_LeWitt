import os
import sys
import psycopg
from dotenv import load_dotenv

def setup_db():
    load_dotenv(override=True)
    
    conn_str = os.getenv("POSTGRES_DB_URI")
    if not conn_str:
        print("POSTGRES_DB_URI not found.")
        sys.exit(1)

    print("Connecting to DB to setup tables...")
    try:
        with psycopg.connect(conn_str, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Create threads table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS threads (
                        thread_id TEXT PRIMARY KEY,
                        title TEXT,
                        summary TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                print("Table 'threads' created or verified.")
                
                # Check if it works
                cur.execute("SELECT count(*) FROM threads;")
                print(f"Current threads count: {cur.fetchone()[0]}")

    except Exception as e:
        print(f"Setup Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup_db()
