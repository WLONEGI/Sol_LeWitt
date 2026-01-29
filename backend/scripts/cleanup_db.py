import os
import sys
import psycopg
from dotenv import load_dotenv

def cleanup_db():
    load_dotenv(override=True)
    
    # Construct DB URL from env
    conn_str = os.getenv("POSTGRES_DB_URI")
    
    if not conn_str:
        print("POSTGRES_DB_URI not found in environment.")
        sys.exit(1)

    print(f"Connecting to DB to cleanup...")
    
    try:
        with psycopg.connect(conn_str, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Check tables first
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name IN ('checkpoints', 'checkpoint_writes', 'checkpoint_blobs');
                """)
                tables = [row[0] for row in cur.fetchall()]
                
                if not tables:
                    print("No LangGraph tables found. Nothing to cleanup.")
                    return

                print(f"Found tables: {tables}")
                
                if "--force" not in sys.argv:
                    confirmation = input("Are you sure you want to delete all data from these tables? (y/N): ")
                    if confirmation.lower() != 'y':
                        print("Cleanup cancelled.")
                        return
                else:
                    print("Force flag detected. Proceeding without confirmation.")

                # Truncate tables
                print("Truncating tables...")
                # Use TRUNCATE CASCADE to handle foreign keys if any
                cur.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE;")
                
                print("Cleanup completed successfully.")
                
    except Exception as e:
        print(f"Cleanup Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    cleanup_db()
