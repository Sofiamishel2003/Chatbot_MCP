# Console Chatbot Host (Multi‑MCP, Context, Logging)

Natural‑language **console chatbot** that connects to **multiple MCP servers** over STDIO and uses an **LLM API** to understand user intent, call tools, and answer in plain English/Spanish. It **keeps conversational context** and **logs every MCP interaction** (requests & responses) to a JSONL file.

> Designed for class requirements:  
> - Maintain and show a **log** of all interactions with MCP servers.  
> - Maintain **context** in a session (e.g., “Who was Alan Turing?” → “In what year was he born?”).  
> - Use **natural language**; the host decides when to call MCP tools.  
> - Support **more than one** MCP server (the movies server and others).

---

## 1) Features
- 🧠 **LLM‑driven chat** (Anthropic by default; OpenAI optional if you adapt `llm_client.py`).
- 🧰 **Multi‑MCP**: loads N servers from `servers.config.json` and namespaces tools.
- 🔗 **Tool calling**: the LLM decides when to call a tool; the host executes it and converts JSON to natural‑language answers.
- 🧾 **Full logging**: writes **every** MCP interaction to `logs/mcp_log.jsonl` (connect, list_tools, call_tool.request, call_tool.response, and LLM tool_use/final_response).
- 💬 **Session context**: keeps message history so follow‑ups refer to prior topics.
- 🧩 **Safe tool names**: tools are exposed as `server__tool` (no dots) to comply with provider regex rules.

---

## 2) Repository layout (relevant files)
```
project-root/
├─ chat.py                # ← console chatbot host (entry point)
├─ mcp_logger.py          # ← JSONL logger used by the host
├─ servers.config.json    # ← list of MCP servers to launch via STDIO
├─ mcp_servers/
│  └─ movies/             # your Movie MCP server lives here
│     ├─ movie_server.py  # exposes tools like search_movie, recommend_movies_tool, etc.
│     └─ datasets/        # movies_metadata.csv, keywords.csv (credits.csv optional)
└─ logs/
   └─ mcp_log.jsonl       # created at runtime
```

> The host is **generic**: it will work with your movies server and any other MCP servers listed in `servers.config.json`.

---

## 3) Installation

### Prerequisites
- **Python 3.10+**
- A valid **LLM API key** (Anthropic recommended).

### Setup
```powershell
# Windows PowerShell inside your venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
pip install mcp[cli] anthropic rich python-dotenv
```

Create a `.env` file next to `chat.py` with your key:
```
ANTHROPIC_API_KEY=sk-ant-xxxxxxx
```

> `chat.py` loads `.env` automatically (via `python-dotenv`).
---

## 4) Configure MCP servers

Edit **`servers.config.json`** to include all servers you need. Example:
```json
{
  "servers": [
    {
      "name": "movie_server",
      "command": "python",
      "args": ["mcp_servers/movies/movie_server.py", "stdio"],
      "env": {}
    },
    {
      "name": "fs",
      "command": "uvx",
      "args": ["mcp", "run", "filesystem"],
      "env": {}
    }
  ]
}
```

- `name`: logical server name (letters/numbers/underscore/hyphen).  
- `command` and `args`: how to start the MCP server via **STDIO**.  
- `env`: optional environment variables (e.g., dataset paths).

> The host will **namespace** tools as `movie_server__search_movie`, `fs__read`, etc.

---

## 5) Run the console host

```powershell
python chat.py
```
You should see:
```
Chatbot MCP ready. Type /help for commands.
```

### Built‑in commands
- `/servers` — list connected servers.  
- `/tools <server>` — list tools from one server.  
- `/logpath` — show the log file path.  
- `/history` — show message count in session.  
- `/clear` — clear conversation context.  
- `/help` — show this help.

---

## 6) What to expect (flow)

1. You ask in **natural language**.  
2. The LLM may return `tool_use` calls.  
3. The host executes `server__tool` on the correct MCP server and appends `tool_result`.  
4. The LLM then produces a **final natural‑language answer** for you.  
5. All MCP steps are **logged** to `logs/mcp_log.jsonl`.

**Logging format** (JSONL, one event per line):
```json
{"ts":"2025-09-03T17:22:44.10Z","event":"connect","payload":{"server":"movie_server","command":"python","args":["..."]}}
{"ts":"2025-09-03T17:22:44.13Z","event":"list_tools","payload":{"server":"movie_server","tools":["search_movie", "..."]}}
{"ts":"2025-09-03T17:23:01.55Z","event":"llm.tool_use","payload":{"name":"movie_server__search_movie","args":{"query":"Toy Story","limit":5}}}
{"ts":"2025-09-03T17:23:01.70Z","event":"call_tool.request","payload":{"server":"movie_server","tool":"search_movie","args":{"query":"Toy Story","limit":5}}}
{"ts":"2025-09-03T17:23:02.01Z","event":"call_tool.response","payload":{"server":"movie_server","tool":"search_movie","structured":{...}}}
{"ts":"2025-09-03T17:23:02.50Z","event":"llm.final_response","payload":{"text":"Here are the movies..."}}}
```

---

## 7) Quick test script (context + movies)

> Titles/genres are best provided in **English** for MovieLens/TMDB.

### A) Context only (no tools)
1. `Who was Alan Turing?`  
2. `And in what year was he born?`  
3. `Summarize his main contributions in two lines.`

### B) Movies (should call MCP)
1. `Search for "Toy Story" and list the title, year and average rating.`  
2. `Give me more details about the first one.`  
3. `What year was it released and what's the runtime?`

### C) Recommendations
1. `Recommend science fiction movies with rating >= 7.5 from 2000 to 2020. Return 8 items.`  
2. `Now restrict to English only.`  
3. `Also include Adventure as a genre.`

### D) Similar by keywords
1. `Find 8 movies similar to "The Dark Knight" based on keywords.`  
2. `From that list, which one has the highest rating?`

### E) Playlist by minutes
1. `Build me an 8-hour watchlist of Drama/Thriller films. Prefer high ratings.`  
2. `Make it English only.`

---

## 9) Notes & references
- **MCP Architecture** (how hosts and servers interact): modelcontextprotocol.io/docs/learn/architecture  
- **MCP Specification** (JSON‑RPC, STDIO framing, tools): modelcontextprotocol.io/specification/2025-06-18  
- **MCP Servers & SDKs** (reference examples): github.com/modelcontextprotocol/servers

---

## 10) License
For class/demo use. Respect original dataset licenses (TMDB/GroupLens/Kaggle) when using the movies server.
