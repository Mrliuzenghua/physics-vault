"""Submit prepared Obsidian import chunks through the Physics Vault MCP server.

The helper is a tiny stdio MCP client.  It never opens a database connection:
the only write operation is the server's ``submit_ai_generated_review`` tool,
which writes review-workbench tasks rather than canonical questions.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "scripts" / "physics_vault_mcp_server.py"


def _request(process: subprocess.Popen[str], request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("MCP server streams are unavailable")
    process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n")
    process.stdin.flush()
    while True:
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("MCP server exited before replying")
        message = json.loads(line)
        if message.get("id") == request_id:
            if "error" in message:
                raise RuntimeError(str(message["error"]))
            return message.get("result") or {}


def _notify(process: subprocess.Popen[str], method: str, params: dict[str, Any] | None = None) -> None:
    if process.stdin is None:
        raise RuntimeError("MCP server input is unavailable")
    message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params:
        message["params"] = params
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()


def _tool_data(result: dict[str, Any]) -> dict[str, Any]:
    for item in result.get("content") or []:
        if item.get("type") == "text":
            raw = item.get("text") or "{}"
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(raw)
                except (ValueError, SyntaxError) as exc:
                    raise RuntimeError(f"Unexpected MCP tool response: {raw!r}") from exc
                return parsed if isinstance(parsed, dict) else {}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit prepared Obsidian chunks to the review workspace via MCP.")
    parser.add_argument("--chunks-dir", type=Path, required=True)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0, help="Inclusive chunk number; 0 means all")
    args = parser.parse_args()

    chunks = sorted(args.chunks_dir.glob("questions-*.json"))
    if args.end:
        chunks = [path for path in chunks if args.start <= int(path.stem.rsplit("-", 1)[1]) <= args.end]
    else:
        chunks = [path for path in chunks if int(path.stem.rsplit("-", 1)[1]) >= args.start]
    if not chunks:
        raise SystemExit("No import chunk files selected")

    process = subprocess.Popen(
        [sys.executable, str(SERVER)],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    submitted: list[dict[str, Any]] = []
    try:
        _request(
            process,
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "obsidian-review-import", "version": "1.0"},
            },
        )
        _notify(process, "notifications/initialized")
        for number, chunk in enumerate(chunks, start=1):
            relative = chunk.resolve().relative_to(ROOT).as_posix()
            result = _request(
                process,
                number + 1,
                "tools/call",
                {
                    "name": "submit_ai_generated_review",
                    "arguments": {
                        "source_text": f"@file:{relative}",
                        "source": f"Obsidian Vault2 标准题库（批次 {number}/{len(chunks)}）",
                        "chat_context": "来源：Pysics Vault2.0/01-Obsidian/02-题库；图片：data/assets/questions/obsidian-vault2/",
                    },
                },
            )
            data = _tool_data(result)
            if not data.get("task_id"):
                raise RuntimeError(f"{chunk.name}: MCP did not return a review task: {data}")
            submitted.append({"chunk": chunk.name, "task_id": data["task_id"], "question_count": data.get("question_count", 0)})
            print(json.dumps(submitted[-1], ensure_ascii=False))
    finally:
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()

    summary = {
        "chunk_count": len(submitted),
        "question_count": sum(int(item["question_count"] or 0) for item in submitted),
        "task_ids": [item["task_id"] for item in submitted],
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
