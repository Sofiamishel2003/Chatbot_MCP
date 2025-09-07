# MCP File System Server

A secure **Model Context Protocol (MCP)** server exposing common file-system operations inside a sandboxed root. Designed to match the structure and style of your movie MCP server so it plugs right into your existing host.

* Safe sandbox root via `FS_ROOT`
* Virtual working directory via `FS_CWD`
* Tools for list/read/write/append/mkdir/rm/mv/cp/stat/glob/find/replace and cwd management
* FastMCP, Pydantic schemas, and background I/O helpers—same architecture you use in your movie server

## Features

* Sandbox guard: all paths are resolved under `FS_ROOT` (parent escapes blocked)
* Rich tool set for everyday file ops (see **Tools** below)
* Plays nicely with your host’s namespacing → `filesystem__fs_read_file`, etc.
* Works over **STDIO** (recommended)

## Requirements

```
python >= 3.10
mcp >= 1.2.0
pydantic >= 2.7.0
```

Optional (only for your host, not this server): `anthropic`, `httpx`.

## Installation

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install "mcp>=1.2.0" "pydantic>=2.7.0"
```

## Configuration (Sandbox)

Set environment variables before launching:

* `FS_ROOT` — absolute path to your allowed sandbox root (default: process cwd)
* `FS_CWD` — initial working directory **relative to `FS_ROOT`** (default: `.`)
* `FS_TOOL_TIMEOUT` — per-tool timeout in seconds (default: `30.0`)

**Example (PowerShell):**

```powershell
$env:FS_ROOT = "C:\Users\<you>\Projects\my-sandbox"
$env:FS_CWD  = "."
```

## Run (STDIO)

```bash
python filesystem_server.py
```

> You can also run via `python -m mcp run python filesystem_server.py`.

## Tools

All tool names are prefixed `fs_` in the server; your host will namespace them as `filesystem__...`.

* `fs_list_dir(path=".", recursive=False, include_hidden=False, glob=None)`
* `fs_read_file(path, encoding="utf-8", max_bytes=None)`
* `fs_write_file(path, content, encoding="utf-8", overwrite=False, create_dirs=True)`
* `fs_append_file(path, content, encoding="utf-8")`
* `fs_mkdir(path, parents=True, exist_ok=True)`
* `fs_remove(path, recursive=False)`  *(files or dirs)*
* `fs_move(src, dst, overwrite=False)`
* `fs_copy(src, dst, overwrite=False)`
* `fs_stat(path)`  *(size, mtime, perms, readable/writable/executable)*
* `fs_glob(pattern="**/*", base=".")`
* `fs_find_text(pattern, regex=False, glob="**/*", encoding="utf-8", max_matches=100)`
* `fs_replace_text(pattern, replacement, regex=False, glob="**/*", encoding="utf-8", dry_run=True, max_replacements=1000)`
* `fs_get_cwd()`
* `fs_set_cwd(path)`

### Safety model

All user paths are resolved as `resolve(FS_ROOT / FS_CWD / user_path)`. Any attempt to escape the sandbox throws `PermissionError`.

---

## Ejemplos de llamada (payloads)

* **Listar archivos** (no recursivo, solo visibles):

```json
{"path": ".", "recursive": false, "include_hidden": false}
```

* **Listar con glob**:

```json
{"path": ".", "glob": "*.py"}
```

* **Leer archivo**:

```json
{"path": "README.md", "encoding": "utf-8", "max_bytes": 65536}
```

* **Escribir (crea carpetas si no existen)**:

```json
{"path": "notes/todo.txt", "content": "hola\n", "overwrite": true, "create_dirs": true}
```

* **Buscar texto (literal) en todos los .py**:

```json
{"pattern":"FastMCP","regex":false,"glob":"**/*.py","max_matches":50}
```

* **Reemplazar texto (dry-run)**:

```json
{"pattern":"foo","replacement":"bar","regex":false,"glob":"**/*.md","dry_run":true}
```

* **Cambiar cwd virtual**:

```json
{"path":"datasets"}
```