"""
matching_agent.py
LangGraph agent that matches resumes to a job description using tools
served entirely over MCP — this file has no direct filesystem access;
every file operation goes through filesystem_mcp_server.py via JSON-RPC.

API keys used:
    OPENAI_API_KEY   (required) - LLM reasoning, via langchain-openai /
                                    the OpenAI API. Get one at
                                    https://platform.openai.com/api-keys
    TAVILY_API_KEY   (optional) - Part B bonus: connects a SECOND MCP
                                    server (Tavily web search) so the
                                    agent can look up company info while
                                    matching. Get one at https://tavily.com
                                    If unset, the agent simply runs with
                                    the filesystem MCP server only.

Neither key is hardcoded here — both are read from environment variables
(loaded from a local .env file, never committed to source control).
"""

import os
import sys
import shutil
import asyncio
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

load_dotenv()

SYSTEM_PROMPT = """You are a resume-matching assistant. You have MCP tools for
listing, reading, and batch-processing resume files, and for watching a
directory for newly-added resumes. Given a job description and a resumes
directory:
1. List and batch-process resumes in the directory.
2. Score each resume against the job description (skills, experience, keywords).
3. Return a ranked list with a 1-2 sentence justification per resume.
Always use the tools to read actual file contents — never invent resume content.
"""


def _resolve_interpreter() -> str:
    """
    Find a Python interpreter path that Windows' CreateProcess can actually
    launch. sys.executable is correct almost everywhere, but a few Windows
    setups (embeddable installs, some launcher shims) leave it blank or
    pointing at a non-existent path — in which case we fall back to
    searching PATH for python.exe / python3 / the py launcher.
    """
    candidates = [sys.executable, shutil.which("python"),
                  shutil.which("python3"), shutil.which("py")]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise RuntimeError(
        "Could not locate a working Python interpreter to launch the MCP "
        f"server. Tried: {candidates}. Run `python -c \"import sys; "
        "print(sys.executable)\"` in your terminal and check that path exists."
    )


def build_mcp_config() -> dict:
    """
    Defines every MCP server this agent connects to. The filesystem server
    is always launched as a local subprocess speaking JSON-RPC 2.0 over
    stdio. A second server is added only if TAVILY_API_KEY is configured,
    demonstrating the Part B multi-MCP bonus.
    """
    project_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(project_dir, "filesystem_mcp_server.py")
    if not os.path.isfile(server_path):
        raise FileNotFoundError(
            f"filesystem_mcp_server.py not found at {server_path}. "
            "Make sure it's in the same folder as matching_agent.py."
        )

    interpreter = _resolve_interpreter()

    if os.environ.get("MCP_DEBUG"):
        print(f"[debug] interpreter: {interpreter}")
        print(f"[debug] server script: {server_path}")

    config = {
        "filesystem": {
            "command": interpreter,
            "args": [server_path],
            "transport": "stdio",
            "cwd": project_dir,
        }
    }
    if os.environ.get("TAVILY_API_KEY"):
        config["web_search"] = {
            "command": "npx",
            "args": ["-y", "tavily-mcp"],
            "transport": "stdio",
            "env": {"TAVILY_API_KEY": os.environ["TAVILY_API_KEY"]},
        }
    return config


async def run_matching(job_description: str, resumes_dir: str = "resumes") -> str:
    """End-to-end run: discover MCP tools, build the agent, rank resumes."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")

    client = MultiServerMCPClient(build_mcp_config())
    tools = await client.get_tools()  # <- JSON-RPC "tools/list" under the hood

    model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)

    user_message = (
        f"Job description:\n{job_description}\n\n"
        f"Resumes directory: {resumes_dir}\n"
        f"Batch-process the resumes in that directory and rank them against the job description."
    )

    result = await agent.ainvoke({"messages": [{"role": "user", "content": user_message}]})
    return result["messages"][-1].content


async def watch_and_notify(resumes_dir: str = "resumes", timeout_seconds: int = 20) -> str:
    """Demo of the agent invoking the new watch_directory MCP tool directly."""
    client = MultiServerMCPClient(build_mcp_config())
    tools = await client.get_tools()
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)

    result = await agent.ainvoke({
        "messages": [{
            "role": "user",
            "content": (
                f"Watch '{resumes_dir}' for up to {timeout_seconds} seconds "
                f"and tell me if any new resumes appeared."
            ),
        }]
    })
    return result["messages"][-1].content


if __name__ == "__main__":
    job_description = (
        "Senior Backend Engineer - Python, distributed systems, AWS, "
        "5+ years experience."
    )
    output = asyncio.run(run_matching(job_description, resumes_dir="resumes"))
    print(output)
