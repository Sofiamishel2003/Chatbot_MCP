from datetime import datetime
import glob
from pathlib import Path
import os
import shutil
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from filesystem_models import AppendFileParams, CopyParams, FindTextParams, GlobParams, ListDirParams, MkdirParams, MoveParams, ReadFileParams, RemoveParams, ReplaceTextParams, SetCwdParams, StatParams, WriteFileParams


# Raíz segura para todas las operaciones (por defecto, el cwd del proceso)
FS_ROOT = Path(os.getenv("FS_ROOT", os.getcwd())).resolve()
# Directorio de trabajo "virtual" (relativo a FS_ROOT); se guarda en memoria
_CURRENT_REL = Path(os.getenv("FS_CWD", "."))

def _is_within(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False

def _resolve_user_path(user_path: str | Path) -> Path:
    """
    Convierte un path "del usuario" (relativo al CWD virtual) a un Path absoluto
    dentro de FS_ROOT. Bloquea salidas con .. y symlinks escapistas.
    """
    base = FS_ROOT.joinpath(_CURRENT_REL).resolve()
    p = (base / Path(user_path)).resolve()
    if not _is_within(FS_ROOT, p):
        raise PermissionError(f"Path fuera del sandbox: {p}")
    return p

def _rel_to_root(p: Path) -> str:
    """Representación relativa a FS_ROOT para respuestas."""
    try:
        return str(p.resolve().relative_to(FS_ROOT))
    except Exception:
        return str(p)
    
def _entry_dict(p: Path) -> Dict[str, Any]:
    try:
        st = p.stat()
        kind = "dir" if p.is_dir() else "file" if p.is_file() else "other"
        return {
            "path": _rel_to_root(p),
            "name": p.name,
            "type": kind,
            "size": st.st_size if kind == "file" else None,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
        }
    except FileNotFoundError:
        return {"path": _rel_to_root(p), "name": p.name, "type": "missing"}

def _list_dir(params: ListDirParams) -> List[Dict[str, Any]]:
    base = _resolve_user_path(params.path)
    if not base.exists():
        return []
    if params.glob:
        pattern = str((base / params.glob).as_posix())
        paths = [Path(p) for p in glob.glob(
            pattern,
            recursive=(params.recursive or ('**' in params.glob))
        )]
    elif params.recursive:
        paths = [p for p in base.rglob("*")]
    else:
        paths = [p for p in base.iterdir()]

    out = []
    for p in paths:
        if not params.include_hidden and p.name.startswith("."):
            continue
        out.append(_entry_dict(p))
    return out

def _read_file(params: ReadFileParams) -> Dict[str, Any]:
    p = _resolve_user_path(params.path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"No existe archivo: {params.path}")
    raw = p.read_bytes()
    if params.max_bytes is not None:
        raw = raw[: int(params.max_bytes)]
    try:
        text = raw.decode(params.encoding, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    return {"path": _rel_to_root(p), "bytes": len(raw), "text": text}

def _write_file(params: WriteFileParams) -> Dict[str, Any]:
    p = _resolve_user_path(params.path)
    if p.exists() and not params.overwrite:
        raise FileExistsError(f"Ya existe: {params.path} (use overwrite=True)")
    if params.create_dirs:
        p.parent.mkdir(parents=True, exist_ok=True)
    data = params.content.encode(params.encoding, errors="replace")
    p.write_bytes(data)
    return {"path": _rel_to_root(p), "bytes": len(data), "status": "written"}

def _append_file(params: AppendFileParams) -> Dict[str, Any]:
    p = _resolve_user_path(params.path)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    with p.open("a", encoding=params.encoding, errors="replace", newline="") as f:
        f.write(params.content)
    return {"path": _rel_to_root(p), "status": "appended"}

def _mkdir(params: MkdirParams) -> Dict[str, Any]:
    p = _resolve_user_path(params.path)
    p.mkdir(parents=params.parents, exist_ok=params.exist_ok)
    return {"path": _rel_to_root(p), "status": "created"}

def _remove(params: RemoveParams) -> Dict[str, Any]:
    p = _resolve_user_path(params.path)
    if not p.exists():
        return {"path": _rel_to_root(p), "status": "not-found"}
    if p.is_dir():
        if params.recursive:
            shutil.rmtree(p)
        else:
            p.rmdir()
    else:
        p.unlink()
    return {"path": _rel_to_root(p), "status": "removed"}

def _move(params: MoveParams) -> Dict[str, Any]:
    src = _resolve_user_path(params.src)
    dst = _resolve_user_path(params.dst)
    if dst.exists():
        if params.overwrite:
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        else:
            raise FileExistsError(f"Destino ya existe: {params.dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {"src": _rel_to_root(src), "dst": _rel_to_root(dst), "status": "moved"}

def _copy(params: CopyParams) -> Dict[str, Any]:
    src = _resolve_user_path(params.src)
    dst = _resolve_user_path(params.dst)
    if not src.exists():
        raise FileNotFoundError(f"No existe origen: {params.src}")
    if dst.exists() and not params.overwrite:
        raise FileExistsError(f"Destino ya existe: {params.dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=params.overwrite)
    else:
        shutil.copy2(src, dst)
    return {"src": _rel_to_root(src), "dst": _rel_to_root(dst), "status": "copied"}

def _stat(params: StatParams) -> Dict[str, Any]:
    p = _resolve_user_path(params.path)
    st = p.stat()
    mode = st.st_mode
    return {
        "path": _rel_to_root(p),
        "exists": True,
        "is_dir": p.is_dir(),
        "is_file": p.is_file(),
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
        "mode": oct(mode),
        "readable": os.access(p, os.R_OK),
        "writable": os.access(p, os.W_OK),
        "executable": os.access(p, os.X_OK),
    }

def _glob(params: GlobParams) -> List[Dict[str, Any]]:
    base = _resolve_user_path(params.base)
    pattern = str(base / params.pattern)
    paths = [Path(p) for p in glob.glob(pattern, recursive=True)]
    return [_entry_dict(p) for p in paths]

def _find_text(params: FindTextParams) -> List[Dict[str, Any]]:
    base = _resolve_user_path(".")
    pattern = re.compile(params.pattern) if params.regex else None
    matches: List[Dict[str, Any]] = []
    # limitar archivos por glob
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if not Path(_rel_to_root(p)).match(params.glob):
            continue
        try:
            text = p.read_text(encoding=params.encoding, errors="replace")
        except Exception:
            continue
        if params.regex:
            for m in pattern.finditer(text):
                matches.append({"path": _rel_to_root(p), "span": [m.start(), m.end()], "match": m.group(0)})
                if len(matches) >= params.max_matches:
                    return matches
        else:
            idx = 0
            needle = params.pattern
            while True:
                idx = text.find(needle, idx)
                if idx == -1:
                    break
                matches.append({"path": _rel_to_root(p), "span": [idx, idx+len(needle)], "match": needle})
                idx += len(needle)
                if len(matches) >= params.max_matches:
                    return matches
    return matches

def _replace_text(params: ReplaceTextParams) -> Dict[str, Any]:
    base = _resolve_user_path(".")
    total_files = 0
    total_repls = 0
    details: List[Dict[str, Any]] = []

    regex = re.compile(params.pattern) if params.regex else None

    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if not Path(_rel_to_root(p)).match(params.glob):
            continue
        try:
            text = p.read_text(encoding=params.encoding, errors="replace")
        except Exception:
            continue

        if params.regex:
            new_text, n = regex.subn(params.replacement, text)
        else:
            n = text.count(params.pattern)
            new_text = text.replace(params.pattern, params.replacement)

        if n > 0:
            total_files += 1
            total_repls += n
            details.append({"path": _rel_to_root(p), "replacements": n})
            if not params.dry_run:
                p.write_text(new_text, encoding=params.encoding, errors="replace")
        if total_repls >= params.max_replacements:
            break

    return {
        "changed_files": total_files,
        "total_replacements": total_repls,
        "dry_run": params.dry_run,
        "details": details
    }

def _get_cwd() -> Dict[str, Any]:
    return {"cwd": str(_CURRENT_REL), "root": str(FS_ROOT)}

def _set_cwd(params: SetCwdParams) -> Dict[str, Any]:
    global _CURRENT_REL
    new_abs = _resolve_user_path(params.path)
    if not new_abs.exists() or not new_abs.is_dir():
        raise NotADirectoryError(f"No es un directorio: {params.path}")
    # guardamos ruta relativa a FS_ROOT
    _CURRENT_REL = new_abs.resolve().relative_to(FS_ROOT)
    return _get_cwd()
