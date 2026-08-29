"""
filesystem_mcp_server.py
MCP (Model Context Protocol) server exposing filesystem tools for the
resume-matching agent. Implements JSON-RPC 2.0 via the official MCP SDK,
tool + resource discovery, and two new capabilities: watch_directory()
and batch_process().

Run standalone (for manual testing over stdio):
    python filesystem_mcp_server.py

Normally this file is launched as a subprocess by an MCP client
(matching_agent.py / test_scenarios.py) — you do not need to run it
directly yourself.
"""

import os
import time
import glob
import json
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader

mcp = FastMCP("filesystem-mcp-server")

# All file operations are sandboxed under BASE_DIR (defaults to cwd).
BASE_DIR = os.environ.get("MCP_BASE_DIR", os.getcwd())


def _safe_path(path: str) -> str:
    """Resolve a path and make sure it stays inside BASE_DIR."""
    full = os.path.abspath(os.path.join(BASE_DIR, path))
    if not full.startswith(os.path.abspath(BASE_DIR)):
        raise ValueError(f"Path '{path}' escapes the allowed base directory.")
    return full


# ---------------------------------------------------------------------------
# Milestone 1 tools, converted to MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_files(directory: str = ".", pattern: str = "*") -> list[dict]:
    """List files in a directory, optionally filtered by a glob pattern."""
    target = _safe_path(directory)
    if not os.path.isdir(target):
        raise FileNotFoundError(f"Directory not found: {directory}")
    results = []
    for path in glob.glob(os.path.join(target, pattern)):
        stat = os.stat(path)
        results.append({
            "name": os.path.basename(path),
            "path": os.path.relpath(path, BASE_DIR),
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return results


@mcp.tool()
def read_file(path: str) -> str:
    """Read a plain-text file and return its contents."""
    target = _safe_path(path)
    if not os.path.isfile(target):
        raise FileNotFoundError(f"File not found: {path}")
    with open(target, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


@mcp.tool()
def write_file(path: str, content: str) -> dict:
    """Write text content to a file, creating parent directories if needed."""
    target = _safe_path(path)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return {"status": "ok", "path": path, "bytes_written": len(content.encode("utf-8"))}


@mcp.tool()
def get_file_info(path: str) -> dict:
    """Return metadata (size, timestamps, extension) for a file or directory."""
    target = _safe_path(path)
    if not os.path.exists(target):
        raise FileNotFoundError(f"Path not found: {path}")
    stat = os.stat(target)
    return {
        "path": path,
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "extension": os.path.splitext(target)[1].lower(),
        "is_dir": os.path.isdir(target),
    }


@mcp.tool()
def extract_resume_text(path: str) -> str:
    """Extract plain text from a resume file (.pdf, .txt, or .md)."""
    target = _safe_path(path)
    if not os.path.isfile(target):
        raise FileNotFoundError(f"File not found: {path}")
    ext = os.path.splitext(target)[1].lower()
    if ext == ".pdf":
        reader = PdfReader(target)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif ext in (".txt", ".md"):
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported resume format: {ext}")


# ---------------------------------------------------------------------------
# New MCP-specific capabilities
# ---------------------------------------------------------------------------

@mcp.tool()
def watch_directory(directory: str = ".", timeout_seconds: int = 20, poll_interval: float = 1.0) -> dict:
    """
    Poll a directory for newly-added files for up to `timeout_seconds`.
    MCP tool calls are request/response, so this runs a bounded polling
    loop rather than an unbounded background watch — it returns as soon
    as a new file appears or the timeout elapses.
    """
    target = _safe_path(directory)
    if not os.path.isdir(target):
        raise FileNotFoundError(f"Directory not found: {directory}")

    seen = set(os.listdir(target))
    start = time.time()
    new_files = []

    while time.time() - start < timeout_seconds:
        current = set(os.listdir(target))
        added = current - seen
        if added:
            new_files.extend(sorted(added))
            seen = current
            break
        time.sleep(poll_interval)

    return {
        "directory": directory,
        "watched_seconds": round(time.time() - start, 1),
        "new_files": new_files,
        "status": "new_files_found" if new_files else "timeout_no_changes",
    }


@mcp.tool()
def batch_process(directory: str = ".", pattern: str = "*.pdf") -> dict:
    """
    Extract text from every file in `directory` matching `pattern` in a
    single call, so the agent doesn't need one round-trip per resume.
    """
    target = _safe_path(directory)
    if not os.path.isdir(target):
        raise FileNotFoundError(f"Directory not found: {directory}")

    files = glob.glob(os.path.join(target, pattern))
    processed, errors = [], []

    for path in files:
        rel = os.path.relpath(path, BASE_DIR)
        try:
            text = extract_resume_text(rel)
            processed.append({"path": rel, "chars_extracted": len(text), "preview": text[:200]})
        except Exception as exc:
            errors.append({"path": rel, "error": str(exc)})

    return {
        "directory": directory,
        "pattern": pattern,
        "total_files": len(files),
        "processed": processed,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Resource discovery — clients can browse data without invoking a tool call
# ---------------------------------------------------------------------------

@mcp.resource("resumes://list")
def list_resume_resource() -> str:
    """Expose the current resume directory listing as a discoverable resource."""
    files = list_files(".", "*.pdf")
    return json.dumps(files, indent=2)


@mcp.resource("config://server")
def server_config() -> str:
    """Expose server configuration/capabilities for discovery and debugging."""
    return json.dumps({
        "base_dir": BASE_DIR,
        "tools": ["list_files", "read_file", "write_file", "get_file_info",
                  "extract_resume_text", "watch_directory", "batch_process"],
        "protocol": "MCP over JSON-RPC 2.0",
    }, indent=2)


if __name__ == "__main__":
    # Speaks JSON-RPC 2.0 over stdio per the MCP spec. Errors raised in any
    # @mcp.tool() function are automatically converted into JSON-RPC error
    # responses by the SDK, with the exception message and type preserved.
    mcp.run(transport="stdio")
