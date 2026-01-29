
import asyncio
import subprocess
import time
import httpx
import os
import signal
import sys

# Define port to avoid conflict with existing server 8000
PORT = 8001
BASE_URL = f"http://127.0.0.1:{PORT}"

async def run_client():
    print(f"--- Client Starting on {BASE_URL} ---")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check health
        try:
            r = await client.get(f"{BASE_URL}/docs")
            if r.status_code != 200:
                print("Server not ready.")
                return
        except Exception as e:
            print(f"Connection failed: {e}")
            return

        msg1 = [{"role": "user", "content": "こんにちは"}]
        print(f"Sending: {msg1}")
        
        import uuid
        thread_id = f"test_debug_{uuid.uuid4().hex[:8]}"
        print(f"Using Thread ID: {thread_id}")
        
        async with client.stream("POST", f"{BASE_URL}/api/chat/stream", json={
            "messages": msg1,
            "thread_id": thread_id
        }) as r:
            async for line in r.aiter_lines():
                print(f"CLIENT ALIVE: {line}")

async def main():
    # Start Server
    # Load .env manually to ensure subprocess gets it
    from dotenv import load_dotenv
    load_dotenv("backend/.env")
    
    # Kill port 8001
    try:
        subprocess.run(["lsof", "-t", f"-i:{PORT}"], capture_output=True, check=True).stdout
        pid = subprocess.check_output(["lsof", "-t", f"-i:{PORT}"]).decode().strip()
        if pid:
            print(f"Killing process {pid} on port {PORT}")
            subprocess.run(["kill", "-9", pid])
            time.sleep(1)
    except Exception:
        pass

    env = os.environ.copy()
    # Ensure stdout is unbuffered
    env["PYTHONUNBUFFERED"] = "1"
    
    print(f"Starting server on port {PORT}...")
    # Use the venv python
    python_executable = "./backend/.venv/bin/python"
    
    process = subprocess.Popen(
        [python_executable, "backend/server.py"], # Assuming server.py runs uvicorn
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # Merge stderr to stdout
        text=True,
        bufsize=1 # Line buffered
    )
    
    # Needs a custom server.py start command if server.py doesn't take port arg?
    # backend/server.py likely just imports app. Let's start with uvicorn directly.
    process.kill()
    
    cmd = [
        python_executable, "-m", "uvicorn", "src.app.app:app", 
        "--host", "127.0.0.1", 
        "--port", str(PORT),
        "--app-dir", "backend"
    ]
    
    print(f"Command: {' '.join(cmd)}")
    log_file = open("server.log", "w")
    process = subprocess.Popen(
        cmd,
        cwd=os.getcwd(),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    try:
        # Wait for server startup by checking log file
        print("Waiting for server startup...")
        start_time = time.time()
        server_ready = False
        
        while time.time() - start_time < 20:
            if process.poll() is not None:
                print("Server exited early.")
                break
            
            with open("server.log", "r") as f:
                content = f.read()
                if "Application startup complete" in content:
                    server_ready = True
                    break
            time.sleep(1)
        
        if not server_ready:
            print("Server failed to start or timed out.")
            with open("server.log", "r") as f:
                print(f"[SERVER LOG]\n{f.read()}")
            return

        # Run Client
        await run_client()
        
        time.sleep(5)
            
    finally:
        print("Stopping server...")
        try:
            log_file.close()
        except:
            pass
        process.terminate()
        try:
            process.wait(timeout=5)
        except:
            process.kill()
        
        print("--- SERVER LOGS ---")
        try:
            with open("server.log", "r") as f:
                print(f.read())
        except Exception as e:
            print(f"Failed to read logs: {e}")

if __name__ == "__main__":
    asyncio.run(main())
