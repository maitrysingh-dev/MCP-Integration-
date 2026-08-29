"""
test_scenarios.py
Demonstrates MCP tool + resource usage independent of the LLM, plus one
end-to-end agent run.

Run with:  python test_scenarios.py
"""

import asyncio
import os
from langchain_mcp_adapters.client import MultiServerMCPClient
from matching_agent import build_mcp_config, run_matching


async def scenario_1_tool_discovery():
    print("\n--- Scenario 1: MCP tool discovery (JSON-RPC 'tools/list') ---")
    client = MultiServerMCPClient(build_mcp_config())
    tools = await client.get_tools()
    for t in tools:
        print(f"  - {t.name}: {t.description}")


async def scenario_2_batch_process():
    print("\n--- Scenario 2: batch_process() over several resumes ---")
    client = MultiServerMCPClient(build_mcp_config())
    tools = await client.get_tools()
    batch_tool = next(t for t in tools if t.name == "batch_process")
    result = await batch_tool.ainvoke({"directory": "resumes", "pattern": "*.pdf"})
    print(result)


async def scenario_3_watch_directory():
    print("\n--- Scenario 3: watch_directory() detects a new file ---")
    client = MultiServerMCPClient(build_mcp_config())
    tools = await client.get_tools()
    watch_tool = next(t for t in tools if t.name == "watch_directory")
    result = await watch_tool.ainvoke({"directory": "resumes", "timeout_seconds": 5})
    print(result)


async def scenario_4_error_handling():
    print("\n--- Scenario 4: error handling for a missing directory ---")
    client = MultiServerMCPClient(build_mcp_config())
    tools = await client.get_tools()
    list_tool = next(t for t in tools if t.name == "list_files")
    try:
        await list_tool.ainvoke({"directory": "does_not_exist"})
    except Exception as exc:
        print(f"  Caught expected JSON-RPC error: {exc}")


async def scenario_5_end_to_end_agent():
    print("\n--- Scenario 5: end-to-end agent run (requires OPENAI_API_KEY) ---")
    if not os.environ.get("OPENAI_API_KEY"):
        print("  Skipped (OPENAI_API_KEY not set).")
        return
    output = await run_matching(
        "Looking for a Python backend engineer with AWS and distributed systems experience.",
        resumes_dir="resumes",
    )
    print(output)


async def main():
    os.makedirs("resumes", exist_ok=True)
    await scenario_1_tool_discovery()
    await scenario_2_batch_process()
    await scenario_3_watch_directory()
    await scenario_4_error_handling()
    await scenario_5_end_to_end_agent()


if __name__ == "__main__":
    asyncio.run(main())
