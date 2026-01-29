import asyncio
import logging
import os
import sys
import uuid
from typing import Any

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from src.shared.config.settings import settings
from src.infrastructure.llm.llm import get_llm_by_type
from src.infrastructure.storage.gcs import upload_to_gcs, download_blob_as_bytes
from src.core.workflow.service import WorkflowManager

# Configure logging to show info in console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("verify_gcp")

async def test_ai_connectivity():
    logger.info("--- Testing AI (Vertex AI/Gemini) Connectivity ---")
    results = {}
    
    models_to_test = ["basic", "reasoning"]
    for model_type in models_to_test:
        try:
            logger.info(f"Testing model type: {model_type}...")
            llm = get_llm_by_type(model_type)
            # Simple prompt to verify basic round-trip
            response = await llm.ainvoke("Say 'Connection Successful' in one word.")
            content = response.content.strip()
            logger.info(f"✅ {model_type} response: {content}")
            results[model_type] = {"status": "SUCCESS", "response": content}
        except Exception as e:
            logger.error(f"❌ {model_type} failed: {e}")
            results[model_type] = {"status": "FAILED", "error": str(e)}
            
    return results

async def test_gcs_connectivity():
    logger.info("--- Testing GCS (Cloud Storage) Connectivity ---")
    if not settings.GCS_BUCKET_NAME:
        logger.error("❌ GCS_BUCKET_NAME is not set.")
        return {"status": "FAILED", "error": "GCS_BUCKET_NAME not set"}
    
    test_filename = f"verify_conn_{uuid.uuid4()}.txt"
    test_content = b"Verification test data"
    
    try:
        # 1. Upload
        logger.info(f"Uploading dummy file to bucket: {settings.GCS_BUCKET_NAME}...")
        public_url = await asyncio.to_thread(
            upload_to_gcs,
            test_content,
            content_type="text/plain",
            session_id="verification_test"
        )
        logger.info(f"✅ Uploaded. Public URL (if applicable): {public_url}")
        
        # 2. Download (using the URL)
        logger.info("Downloading file back...")
        downloaded_content = await asyncio.to_thread(download_blob_as_bytes, public_url)
        
        if downloaded_content == test_content:
            logger.info("✅ Downloaded content matches.")
            return {"status": "SUCCESS", "url": public_url}
        else:
            logger.error("❌ Content mismatch.")
            return {"status": "FAILED", "error": "Content mismatch"}
            
    except Exception as e:
        logger.error(f"❌ GCS test failed: {e}")
        return {"status": "FAILED", "error": str(e)}

async def test_db_connectivity():
    logger.info("--- Testing DB (Cloud SQL/Postgres) Connectivity ---")
    if not settings.POSTGRES_DB_URI:
        logger.error("❌ POSTGRES_DB_URI is not set.")
        return {"status": "FAILED", "error": "POSTGRES_DB_URI not set"}
    
    manager = WorkflowManager()
    try:
        logger.info("Initializing WorkflowManager (DB Pool & Checkpointer)...")
        await manager.initialize()
        
        # Verify pool is open
        if manager.pool and not manager.pool.closed:
            logger.info("✅ DB Connection Pool initialized and open.")
            
            # Simple query to verify
            async with manager.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    res = await cur.fetchone()
                    if res and res[0] == 1:
                        logger.info("✅ SELECT 1 query successful.")
                    else:
                        logger.warning("⚠️ DB connection established but query returned unexpected result.")
            
            await manager.close()
            return {"status": "SUCCESS"}
        else:
            logger.error("❌ DB Pool initialized but closed or None.")
            return {"status": "FAILED", "error": "Pool closed or None"}
            
    except Exception as e:
        logger.error(f"❌ DB test failed: {e}")
        return {"status": "FAILED", "error": str(e)}

async def main():
    logger.info("Starting GCP Connectivity Verification...")
    
    final_report = {
        "AI": await test_ai_connectivity(),
        "GCS": await test_gcs_connectivity(),
        "DB": await test_db_connectivity()
    }
    
    logger.info("\n=== FINAL VERIFICATION REPORT ===")
    for service, status in final_report.items():
        logger.info(f"{service}: {status}")
    
    # Check if any failure occurred
    has_failure = False
    if any(s.get("status") == "FAILED" for s in final_report.values() if isinstance(s, dict)):
        has_failure = True
    if any(item.get("status") == "FAILED" for item in final_report["AI"].values()):
        has_failure = True
        
    if has_failure:
        logger.error("❌ Verification failed for one or more services.")
        sys.exit(1)
    else:
        logger.info("✅ All services verified successfully.")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
