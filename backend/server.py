import uvicorn
import os

if __name__ == "__main__":
    # Local development entry point
    # In production (Docker), gunicorn/uvicorn should run `src.app.app:app` directly.
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "true").lower() == "true"
    
    uvicorn.run(
        "src.app.app:app",
        host=host,
        port=port,
        reload=reload
    )
