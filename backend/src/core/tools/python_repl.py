import logging
import os
from typing import Annotated, Optional
from langchain_core.tools import tool
from langchain_experimental.utilities import PythonREPL

logger = logging.getLogger(__name__)

# Initialize REPL
repl = PythonREPL()

@tool
def python_repl_tool(
    code: Annotated[str, "The python code to execute to do analysis or calculation."],
    work_dir: Annotated[str, "Working directory for file I/O during execution."] = "/tmp",
    expected_files: Annotated[Optional[list[str]], "Optional expected output filenames for result checks."] = None,
):
    """
    Execute python code in a local working directory to perform analysis or calculations.
    Use this for data processing, math, or complex logic.
    File upload/download is handled by the Data Analyst node, not this tool.
    To see the output, use print(...).
    """
    logger.info("Executing Python code in work_dir=%s", work_dir)

    safe_work_dir = os.path.abspath(work_dir or "/tmp")
    os.makedirs(safe_work_dir, exist_ok=True)

    old_cwd = os.getcwd()
    try:
        before_files = {
            name for name in os.listdir(safe_work_dir)
            if os.path.isfile(os.path.join(safe_work_dir, name))
        }

        os.chdir(safe_work_dir)
        result = repl.run(code)

        after_files = {
            name for name in os.listdir(safe_work_dir)
            if os.path.isfile(os.path.join(safe_work_dir, name))
        }
        created_files = sorted(after_files - before_files)

        files_msg = ""
        if created_files:
            files_msg = "\n\nCreated files:\n" + "\n".join(created_files)

        if expected_files:
            missing = [name for name in expected_files if name not in after_files]
            if missing:
                files_msg += "\n\nMissing expected files:\n" + "\n".join(missing)

        return f"Successfully executed.\nStdout: {result}{files_msg}"
    except Exception as e:
        error_msg = f"Failed to execute. Error: {repr(e)}"
        logger.error(error_msg)
        return error_msg
    finally:
        os.chdir(old_cwd)
