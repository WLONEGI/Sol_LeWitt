import os
import sys
import psycopg
from dotenv import load_dotenv

def verify_db_connection():
    load_dotenv(override=True)
    
    # Construct DB URL from env
    conn_str = os.getenv("POSTGRES_DB_URI")
    
    if not conn_str:
        print("POSTGRES_DB_URI not found in environment.")
        sys.exit(1)

    print(f"Connecting to DB...")
    
    try:
        # conn_str is already full URI
        with psycopg.connect(conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                res = cur.fetchone()
                print(f"Connection Successful! Query result: {res}")
                
            # Optional: Check if appropriate tables exist
            # cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
            # print("Tables:", cur.fetchall())
    except Exception as e:
        print(f"Connection Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_db_connection()
