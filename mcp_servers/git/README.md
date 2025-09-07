# Git MCP Server

A Model Context Protocol (MCP) server that exposes common **Git** operations as tools. It’s designed to be used by an MCP-aware host (e.g., your console chatbot or Streamlit UI) so an LLM can **initialize repos, stage/commit files, create branches, inspect status/logs, manage remotes, push/pull**, and more — with structured confirmations.

> Works great together with your File System MCP server to create/edit files and then commit them via Git.

## Features

* Initialize repositories (non-bare)
* Add (stage) files, commit (with optional author)
* Create/check out branches
* Show status, log, diff, tracked files
* Add remotes, push, pull, clone
* Clear, structured results ready to display to end-users

---

## Requirements

* Python 3.10+
* `mcp` (and your project’s deps)
* Git installed and on `PATH` (Windows/macOS/Linux)

---

## Running the server (STDIO)

The Git server is intended to run as a **local STDIO MCP server**.

```bash
# From the repo root (where pyproject.toml lives)
uv run python mcp_servers/git_server.py
```

> Adjust the path if your file is elsewhere (e.g., `git_server.py` in another folder).

---

## Registering the server in your host

Add an entry to your `servers.config.json`:

```json
{
  "servers": [
    {
      "name": "git_server",
      "transport": "stdio",
      "command": "uv",
      "args": ["run", "python", "mcp_servers/git_server.py"],
      "env": {}
    }
  ]
}
```

Then run your host (console chatbot or Streamlit UI). On connect, the host will list tools from `git_server`.

---

## Available Tools & Input Schemas

> Tool names below are what the MCP server exposes. If your host namespaces them as `git_server__<tool>`, use that namespaced name when calling.

### `git_init`

Initialize a repository.

```json
{
  "path": "path/to/repo",
  "bare": false
}
```

### `git_status`

Show repository status.

```json
{
  "path": "path/to/repo"
}
```

### `git_add`

Stage files (supports patterns).

```json
{
  "path": "path/to/repo",
  "patterns": ["README.md", "src/**/*.py"]
}
```

### `git_commit`

Create a commit.

```json
{
  "path": "path/to/repo",
  "message": "Your commit message",
  "author": "Full Name <email@domain.com>"   // optional but recommended on fresh repos
}
```

### `git_branch_create`

Create a branch.

```json
{
  "path": "path/to/repo",
  "name": "feature/x",
  "from": "HEAD"   // optional; defaults to HEAD
}
```

### `git_checkout`

Checkout a branch or commit.

```json
{
  "path": "path/to/repo",
  "ref": "feature/x"
}
```

### `git_log`

Show recent commits.

```json
{
  "path": "path/to/repo",
  "max_count": 10
}
```

### `git_diff`

Diff between refs or working tree.

```json
{
  "path": "path/to/repo",
  "a": "HEAD~1",          // optional
  "b": "HEAD",            // optional
  "pathspecs": ["README.md"] // optional
}
```

### `git_ls_files`

List tracked files.

```json
{
  "path": "path/to/repo"
}
```

### `git_remote_add`

Add a remote.

```json
{
  "path": "path/to/repo",
  "name": "origin",
  "url": "https://github.com/user/repo.git",
  "overwrite": false
}
```

### `git_push`

Push current branch (optionally set upstream).

```json
{
  "path": "path/to/repo",
  "remote": "origin",
  "branch": "feature/x",     // optional; defaults to current
  "set_upstream": true       // optional
}
```

### `git_pull`

Pull from remote.

```json
{
  "path": "path/to/repo",
  "remote": "origin",
  "branch": "main"           // optional; defaults to current
}
```

### `git_clone`

Clone a repository.

```json
{
  "url": "https://github.com/user/repo.git",
  "path": "path/to/clone/here"
}
```