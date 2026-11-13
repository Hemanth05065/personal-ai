import json
from dataclasses import dataclass
from pathlib import Path

from backend.core.config import Settings


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolResult:
    summary: str
    data: dict | list | str

    def serialize(self) -> str:
        return json.dumps({"summary": self.summary, "data": self.data}, ensure_ascii=False)


SUPPORTED_TOOLS = {"information", "list_files", "read_file", "search_files", "write_file"}
TOOL_RISKS = {"information": 0, "list_files": 1, "read_file": 1, "search_files": 1, "write_file": 2}


def _workspace(settings: Settings) -> Path:
    root = settings.workspace_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_workspace_path(settings: Settings, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ToolError("A relative workspace path is required.")
    root = _workspace(settings)
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise ToolError("The requested path is outside the authorized workspace.")
    return target


def list_files(settings: Settings) -> ToolResult:
    root = _workspace(settings)
    files = []
    for item in sorted(root.rglob("*")):
        if item.is_file() and not item.is_symlink():
            stat = item.stat()
            files.append(
                {
                    "path": item.relative_to(root).as_posix(),
                    "size": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )
        if len(files) >= 500:
            break
    return ToolResult(f"Found {len(files)} workspace files.", files)


def read_file(settings: Settings, arguments: dict) -> ToolResult:
    target = resolve_workspace_path(settings, str(arguments.get("path", "")))
    if not target.is_file():
        raise ToolError("File not found in the authorized workspace.")
    size = target.stat().st_size
    if size > settings.max_file_bytes:
        raise ToolError(f"File exceeds the {settings.max_file_bytes}-byte reading limit.")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError("Only UTF-8 text files are supported in the MVP workspace.") from exc
    return ToolResult(f"Read {target.name} ({size} bytes).", {"path": arguments["path"], "content": content, "size": size})


def write_file(settings: Settings, arguments: dict) -> ToolResult:
    path = str(arguments.get("path", ""))
    content = str(arguments.get("content", ""))
    encoded = content.encode("utf-8")
    if len(encoded) > settings.max_file_bytes:
        raise ToolError(f"Content exceeds the {settings.max_file_bytes}-byte writing limit.")
    target = resolve_workspace_path(settings, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return ToolResult(f"Wrote {len(encoded)} bytes to {path}.", {"path": path, "size": len(encoded)})


def execute_tool(tool_name: str, arguments: dict, settings: Settings) -> ToolResult:
    if tool_name == "information":
        return ToolResult("Information task recorded; no external action was required.", {})
    if tool_name == "list_files":
        return list_files(settings)
    if tool_name == "read_file":
        return read_file(settings, arguments)
    if tool_name == "write_file":
        return write_file(settings, arguments)
    if tool_name == "search_files":
        from backend.services.search import search_workspace  # search imports this module

        return search_workspace(settings, arguments)
    raise ToolError(f"Unsupported tool: {tool_name}")
