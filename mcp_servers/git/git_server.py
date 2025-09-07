# git_server.py
import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from git import Repo, InvalidGitRepositoryError, NoSuchPathError, GitCommandError, Actor

logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)

mcp = FastMCP("Git MCP Server")

def _abs(p: str) -> Path:
    # Resuelve rutas relativas al CWD del proceso (tu host puede cambiar CWD con filesystem_server)
    return Path(p).expanduser().resolve()

def _open_repo(repo_path: str) -> Repo:
    path = _abs(repo_path)
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    try:
        return Repo(path)
    except InvalidGitRepositoryError:
        raise RuntimeError(f"Not a git repository: {path}")

def _branch_name(repo: Repo) -> Optional[str]:
    try:
        return repo.active_branch.name
    except Exception:
        return None  # detached HEAD o repo recién inicializado

# Herramientas que resuelven
@mcp.tool()
def git_init(path: str, bare: bool = False) -> Dict[str, Any]:
    """
    Initialize a new git repository at `path`.
    Returns: { path, bare, created: bool }
    """
    p = _abs(path)
    p.mkdir(parents=True, exist_ok=True)
    repo = Repo.init(p, bare=bare)
    logger.info(f"Initialized repo at {p} (bare={bare})")
    return {"path": str(p), "bare": bare, "created": True}

@mcp.tool()
def git_status(path: str) -> Dict[str, Any]:
    """
    Show working tree status.
    Returns: { branch, staged, unstaged, untracked }
    """
    repo = _open_repo(path)
    # staged vs unstaged
    try:
        head = repo.head.commit
        staged = [d.b_path for d in repo.index.diff(head)]
    except Exception:
        # Sin commits aún: todo lo agregado en index se considera staged
        staged = [d.b_path for d in repo.index.diff(None)]
    unstaged = [d.a_path for d in repo.index.diff(None)]  # cambios en WT no indexados
    untracked = list(repo.untracked_files)
    return {
        "branch": _branch_name(repo),
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }

@mcp.tool()
def git_add(path: str, patterns: List[str]) -> Dict[str, Any]:
    """
    Stage files. `patterns` may include globs (e.g., ["README.md", "src/**/*.py"])
    """
    repo = _open_repo(path)
    try:
        repo.index.add(patterns)
        return {"path": str(_abs(path)), "added": patterns}
    except GitCommandError as e:
        return {"error": str(e), "path": str(_abs(path)), "patterns": patterns}

@mcp.tool()
def git_commit(
    path: str,
    message: str,
    author_name: Optional[str] = None,
    author_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Commit staged changes with message (and optional author).
    Returns: { commit, message, author }
    """
    repo = _open_repo(path)
    author = None
    if author_name and author_email:
        author = Actor(author_name, author_email)
    try:
        commit = repo.index.commit(message, author=author, committer=author)
        return {
            "commit": commit.hexsha,
            "message": message,
            "author": f"{author_name} <{author_email}>" if author else None,
        }
    except GitCommandError as e:
        return {"error": str(e)}

@mcp.tool()
def git_branch_create(path: str, name: str, checkout: bool = False) -> Dict[str, Any]:
    """
    Create a branch (optionally checkout).
    """
    repo = _open_repo(path)
    try:
        repo.git.branch(name)
        if checkout:
            repo.git.checkout(name)
        return {"path": str(_abs(path)), "branch": name, "checked_out": checkout}
    except GitCommandError as e:
        return {"error": str(e)}

@mcp.tool()
def git_checkout(path: str, name: str) -> Dict[str, Any]:
    """
    Checkout an existing branch or ref.
    """
    repo = _open_repo(path)
    try:
        repo.git.checkout(name)
        return {"path": str(_abs(path)), "branch": name}
    except GitCommandError as e:
        return {"error": str(e)}

@mcp.tool()
def git_log(path: str, max_count: int = 10) -> List[Dict[str, Any]]:
    """
    Return recent commits.
    """
    repo = _open_repo(path)
    out = []
    try:
        for c in repo.iter_commits(max_count=max_count):
            out.append({
                "hash": c.hexsha[:10],
                "author": f"{c.author.name} <{c.author.email}>",
                "date": c.committed_datetime.isoformat(),
                "message": c.message.strip(),
            })
        return out
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def git_remote_add(path: str, name: str, url: str, overwrite: bool = False) -> Dict[str, Any]:
    """
    Add a remote.
    """
    repo = _open_repo(path)
    try:
        if name in [r.name for r in repo.remotes]:
            if overwrite:
                repo.delete_remote(name)
            else:
                return {"path": str(_abs(path)), "remote": name, "error": "remote exists"}
        repo.create_remote(name, url=url)
        return {"path": str(_abs(path)), "remote": name, "url": url}
    except GitCommandError as e:
        return {"error": str(e)}

@mcp.tool()
def git_push(path: str, remote: str = "origin", branch: Optional[str] = None,
             force: bool = False, set_upstream: bool = False) -> Dict[str, Any]:
    """
    Push current branch (or provided).
    """
    repo = _open_repo(path)
    try:
        branch = branch or _branch_name(repo)
        if branch is None:
            return {"error": "No current branch"}
        args = []
        if force:
            args.append("--force")
        if set_upstream:
            args.append("--set-upstream")
        args += [remote, branch]
        res = repo.git.push(*args)
        return {"path": str(_abs(path)), "remote": remote, "branch": branch, "result": res}
    except GitCommandError as e:
        return {"error": str(e)}

@mcp.tool()
def git_pull(path: str, remote: str = "origin", branch: Optional[str] = None,
             rebase: bool = False) -> Dict[str, Any]:
    """
    Pull from remote branch.
    """
    repo = _open_repo(path)
    try:
        branch = branch or _branch_name(repo)
        if branch is None:
            return {"error": "No current branch"}
        args = []
        if rebase:
            args.append("--rebase")
        args += [remote, branch]
        res = repo.git.pull(*args)
        return {"path": str(_abs(path)), "remote": remote, "branch": branch, "result": res}
    except GitCommandError as e:
        return {"error": str(e)}

@mcp.tool()
def git_diff(path: str, commit_a: Optional[str] = None, commit_b: Optional[str] = None,
             name_only: bool = False, cached: bool = False) -> Dict[str, Any]:
    """
    Show diffs between commits or working tree.
    """
    repo = _open_repo(path)
    try:
        args = []
        if name_only:
            args.append("--name-only")
        if cached:
            args.append("--cached")
        if commit_a and commit_b:
            args.append(f"{commit_a}..{commit_b}")
        elif commit_a:
            args.append(commit_a)
        # else: diff WT
        text = repo.git.diff(*args)
        return {"path": str(_abs(path)), "diff": text}
    except GitCommandError as e:
        return {"error": str(e)}

@mcp.tool()
def git_ls_files(path: str) -> List[str]:
    """
    List tracked files.
    """
    repo = _open_repo(path)
    try:
        return repo.git.ls_files().splitlines()
    except GitCommandError as e:
        return [f"error: {e}"]

@mcp.tool()
def git_clone(url: str, dest: str, depth: Optional[int] = None) -> Dict[str, Any]:
    """
    Clone a repository into `dest`.
    """
    d = _abs(dest)
    try:
        kwargs = {}
        if depth:
            kwargs["depth"] = int(depth)
        Repo.clone_from(url, d, **kwargs)
        return {"dest": str(d), "url": url, "depth": depth}
    except GitCommandError as e:
        return {"error": str(e), "dest": str(d), "url": url}

# --- Run server ------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
