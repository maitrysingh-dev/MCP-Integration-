# MCP Resume Matching — Milestone 2

Converts the Milestone 1 filesystem tools into a proper MCP (Model Context
Protocol) server, and refactors the LangGraph matching agent to talk to
that server as an MCP client instead of calling the filesystem directly.

## Files

| File | Part | What it does |
|---|---|---|
| `filesystem_mcp_server.py` | A | JSON-RPC 2.0 MCP server. Exposes `list_files`, `read_file`, `write_file`, `get_file_info`, `extract_resume_text` (Milestone 1 tools) plus new `watch_directory()` and `batch_process()`. Also exposes two discoverable resources (`resumes://list`, `config://server`). |
| `matching_agent.py` | B | LangGraph agent (`create_react_agent`) that connects to the MCP server as a client and uses the discovered tools — no direct filesystem access in this file. |
| `test_scenarios.py` | — | Runnable scenarios: tool discovery, `batch_process`, `watch_directory`, error handling, and a full end-to-end agent run. |
| `workflow_diagram.md` | — | Mermaid sequence + state diagrams of the agent ↔ MCP interaction. |
| `requirements.txt` / `.env.example` | — | Dependencies and required API keys. |

## API keys — where they come from

| Key | Required? | Used for | Get it from |
|---|---|---|---|
| `OPENAI_API_KEY` | **Yes** | The LLM that reasons over resumes and ranks them (`langchain-openai` → OpenAI's `/chat/completions` API, model `gpt-4o-mini`) | https://platform.openai.com/api-keys |
| `TAVILY_API_KEY` | No (bonus only) | Part B bonus — connects a **second** MCP server (Tavily web search) so the agent can look up company/role info while it works | https://app.tavily.com |

Neither key is ever hardcoded in the source. Both are read from environment
variables via `python-dotenv`, loaded from a local `.env` file that you
create yourself and should **not** commit to git.

> If you'd rather use a different LLM provider, swap `ChatOpenAI(...)` in
> `matching_agent.py` for another LangChain chat model (e.g.
> `ChatAnthropic`) and set the matching key instead — the MCP plumbing
> doesn't change.

## Setup in VS Code

1. **Open the folder**
   `File → Open Folder…` → select this project directory.

2. **Create and select a virtual environment** (Terminal in VS Code, `` Ctrl+` ``):
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```
   In VS Code, run **Python: Select Interpreter** (Ctrl+Shift+P) and pick
   `./venv`.

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Add your keys**
   ```bash
   cp .env.example .env
   ```
   Open `.env` and paste in your real `OPENAI_API_KEY` (and optionally
   `TAVILY_API_KEY`).

5. **Add sample resumes**
   ```bash
   mkdir -p resumes
   # drop a few .pdf or .txt resumes into resumes/
   ```

## Running it

You do **not** run `filesystem_mcp_server.py` by itself in normal use —
`matching_agent.py` launches it automatically as a subprocess and talks to
it over stdio via JSON-RPC 2.0.

```bash
# Full agent run (ranks resumes/ against a hardcoded job description)
python matching_agent.py

# All test scenarios (tool discovery, batch_process, watch_directory,
# error handling, end-to-end agent run)
python test_scenarios.py
```

To manually test the server in isolation, launch it with the MCP
inspector (installed via the `mcp[cli]` extra):
```bash
mcp dev filesystem_mcp_server.py
```
This opens a browser UI where you can call each tool and see the raw
JSON-RPC 2.0 requests/responses — useful for the demo video.

## Why this counts as JSON-RPC 2.0 / resource discovery

- The `mcp` SDK's `FastMCP` class implements the full MCP spec, which is
  itself built on JSON-RPC 2.0 — every `tools/list`, `tools/call`, and
  `resources/list` exchange over stdio is a JSON-RPC 2.0 request/response.
- Errors raised inside any `@mcp.tool()` function (e.g. `FileNotFoundError`
  for a bad path) are automatically converted into JSON-RPC 2.0 error
  responses by the SDK, with the message preserved — that's the
  "proper error handling and status codes" requirement.
- `@mcp.resource(...)` decorators (`resumes://list`, `config://server`)
  are what a client calls `resources/list` / `resources/read` against —
  that's the resource discovery endpoint requirement.

## Multi-MCP bonus (Part B)

If `TAVILY_API_KEY` is set in `.env`, `matching_agent.py` automatically
adds a second entry to its MCP config (`web_search`, launched via
`npx -y tavily-mcp`), and the LangGraph agent gets tools from **both**
servers in the same run — demonstrating multi-MCP integration without any
code changes on your end.

## Demo video checklist (5–6 min)

1. Show `filesystem_mcp_server.py` running via `mcp dev` — call `batch_process`
   and `watch_directory` live, point at the JSON-RPC traffic in the inspector.
2. Show `matching_agent.py` connecting as a client (log line: `tools/list`).
3. Run `python test_scenarios.py` end to end.
4. Walk through `workflow_diagram.md`.
5. (Bonus) Add `TAVILY_API_KEY` and show the second MCP server joining.
