from typing import Optional
from pydantic import BaseModel, Field


class ListDirParams(BaseModel):
    path: str = Field(default=".")
    recursive: bool = False
    include_hidden: bool = False
    glob: Optional[str] = None # si se define, ignorar recursive e include_hidden

class ReadFileParams(BaseModel):
    path: str
    encoding: str = "utf-8"
    max_bytes: Optional[int] = None  # si se define, truncar lectura

class WriteFileParams(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"
    overwrite: bool = False
    create_dirs: bool = True

class AppendFileParams(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"

class MkdirParams(BaseModel):
    path: str
    parents: bool = True
    exist_ok: bool = True

class RemoveParams(BaseModel):
    path: str
    recursive: bool = False

class MoveParams(BaseModel):
    src: str
    dst: str
    overwrite: bool = False

class CopyParams(BaseModel):
    src: str
    dst: str
    overwrite: bool = False

class StatParams(BaseModel):
    path: str

class GlobParams(BaseModel):
    pattern: str = "**/*"
    base: str = "."

class FindTextParams(BaseModel):
    pattern: str
    regex: bool = False
    glob: str = "**/*"
    encoding: str = "utf-8"
    max_matches: int = 100

class ReplaceTextParams(BaseModel):
    pattern: str
    replacement: str
    regex: bool = False
    glob: str = "**/*"
    encoding: str = "utf-8"
    dry_run: bool = True
    max_replacements: int = 1000

class SetCwdParams(BaseModel):
    path: str
