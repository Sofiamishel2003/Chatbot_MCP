import os
import io
import re
import sys
import glob
import json
import shutil
import asyncio
import stat as pystat
from typing import Any, Dict, List, Optional, Literal
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP
from filesystem_models import AppendFileParams, CopyParams, FindTextParams, GlobParams, ListDirParams, MkdirParams, MoveParams, ReadFileParams, RemoveParams, ReplaceTextParams, SetCwdParams, StatParams, WriteFileParams
from filesystem_sources import _append_file, _copy, _find_text, _get_cwd, _glob, _list_dir, _mkdir, _move, _read_file, _remove, _replace_text, _set_cwd, _stat, _write_file


mcp = FastMCP("mcp-filesystem")
FS_TOOL_TIMEOUT = float(os.getenv("FS_TOOL_TIMEOUT", "30.0"))

async def _run(fn, *args, timeout: Optional[float] = None):
    to = timeout if timeout is not None else FS_TOOL_TIMEOUT
    return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=to)

# Herramientas que resuelven
@mcp.tool()
async def fs_list_dir(params: ListDirParams) -> List[Dict[str, Any]]:
    """List directory contents. Supports recursive and glob filters."""
    return await _run(_list_dir, params)

@mcp.tool()
async def fs_read_file(params: ReadFileParams) -> Dict[str, Any]:
    """Read a text file. Optionally limit bytes and set encoding."""
    return await _run(_read_file, params)

@mcp.tool()
async def fs_write_file(params: WriteFileParams) -> Dict[str, Any]:
    """Write text to a file. Can create dirs and control overwrite."""
    return await _run(_write_file, params)

@mcp.tool()
async def fs_append_file(params: AppendFileParams) -> Dict[str, Any]:
    """Append text to a file (creates file if missing)."""
    return await _run(_append_file, params)

@mcp.tool()
async def fs_mkdir(params: MkdirParams) -> Dict[str, Any]:
    """Create a directory."""
    return await _run(_mkdir, params)

@mcp.tool()
async def fs_remove(params: RemoveParams) -> Dict[str, Any]:
    """Remove file or directory (use recursive=True for folders)."""
    return await _run(_remove, params)

@mcp.tool()
async def fs_move(params: MoveParams) -> Dict[str, Any]:
    """Move or rename files/directories (supports overwrite)."""
    return await _run(_move, params)

@mcp.tool()
async def fs_copy(params: CopyParams) -> Dict[str, Any]:
    """Copy files/directories (supports overwrite)."""
    return await _run(_copy, params)

@mcp.tool()
async def fs_stat(params: StatParams) -> Dict[str, Any]:
    """Get file/directory metadata: size, mtime, mode, perms."""
    return await _run(_stat, params)

@mcp.tool()
async def fs_glob(params: GlobParams) -> List[Dict[str, Any]]:
    """Glob search relative to a base (default cwd)."""
    return await _run(_glob, params)

@mcp.tool()
async def fs_find_text(params: FindTextParams) -> List[Dict[str, Any]]:
    """Find occurrences of a pattern (literal/regex) in files matching a glob."""
    return await _run(_find_text, params)

@mcp.tool()
async def fs_replace_text(params: ReplaceTextParams) -> Dict[str, Any]:
    """Replace a pattern (literal/regex) across files matching a glob; dry-run supported."""
    return await _run(_replace_text, params)

@mcp.tool()
async def fs_get_cwd() -> Dict[str, Any]:
    """Return current working directory (virtual) and sandbox root."""
    return await _run(_get_cwd)

@mcp.tool()
async def fs_set_cwd(params: SetCwdParams) -> Dict[str, Any]:
    """Change current working directory (virtual) within sandbox root."""
    return await _run(_set_cwd, params)

if __name__ == "__main__":
    mcp.run()
