import logging
import subprocess
import os
import re
from typing import Annotated
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# BLACKLISTED COMMANDS
COMMAND_BLACKLIST = {
    "rm", "mv", "cp", "dd", "chmod", "chown", "passwd", 
    "sudo", "su", "apt", "pip", "npm", "yarn", "docker", 
    "kill", "reboot", "shutdown", "wget", "git"
}

# RESTRICTED PATHS (No writing/modifying these)
RESTRICTED_PATHS = [
    "/etc", "/usr", "/var", "/bin", "/sbin", "/lib", "/app/src"
]

@tool
def bash_tool(
    cmd: Annotated[str, "The bash command to be executed."],
    work_dir: Annotated[str, "Internal: The current working directory."] = "/app",
):
    """
    Execute a bash command in a restricted environment.
    Use this for file system exploration, environment checks, and system operations.
    Restrictions: No file deletion, no system modification, no Git operations.
    """
    logger.info(f"Executing Bash Command: {cmd} in {work_dir}")
    
    # ... filtering logic ...
    
    # 1. Simple command-based filtering
    first_word = cmd.split()[0] if cmd.strip() else ""
    if first_word in COMMAND_BLACKLIST:
        return f"Error: Command '{first_word}' is blacklisted for security reasons."
    
    # 2. Path-based filtering (heuristic)
    # Check for redirection or piping to restricted paths
    for path in RESTRICTED_PATHS:
        if path in cmd and any(char in cmd for char in (">", "|", ">>")):
            return f"Error: Operations involving restricted path '{path}' are forbidden."

    # 3. Execution
    try:
        # Run in work_dir
        result = subprocess.run(
            cmd, shell=True, check=True, text=True, capture_output=True, timeout=30, cwd=work_dir
        )
        output = result.stdout
        if result.stderr:
            output += f"\nStderr:\n{result.stderr}"
        return output or "Success (No output)"
    except subprocess.CalledProcessError as e:
        error_message = f"Command failed with exit code {e.returncode}.\nStdout: {e.stdout}\nStderr: {e.stderr}"
        logger.error(error_message)
        return error_message
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        error_message = f"Error executing command: {str(e)}"
        logger.error(error_message)
        return error_message
