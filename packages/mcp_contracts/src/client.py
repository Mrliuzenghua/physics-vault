from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from .config import MCPConfig
from .errors import AppError
from .logger import MCPCallLogger
from .schemas import BaseResponseModel


@dataclass(slots=True)
class McpCallOptions:
    timeout_ms: int = 20000
    retry_times: int = 1
    trace_id: str | None = None


class McpClient:
    """Abstract MCP client with optional logging support."""

    def __init__(self, config: MCPConfig | None = None) -> None:
        self._config = config or MCPConfig()
        self._logger = MCPCallLogger(self._config)

    @property
    def mode(self) -> str:
        raise NotImplementedError

    async def call(self, tool_name: str, payload: dict[str, Any], options: McpCallOptions | None = None) -> BaseResponseModel:
        raise NotImplementedError


class StdioMcpClient(McpClient):
    def __init__(
        self,
        command_map: dict[str, str],
        cwd: str | None = None,
        config: MCPConfig | None = None,
    ) -> None:
        super().__init__(config)
        self._command_map = command_map
        self._cwd = cwd

    @property
    def mode(self) -> str:
        return "stdio"

    async def call(self, tool_name: str, payload: dict[str, Any], options: McpCallOptions | None = None) -> BaseResponseModel:
        opts = options or McpCallOptions()
        command = self._command_map.get(tool_name) or self._command_map.get("*")
        if not command:
            err = AppError(code="MCP_TOOL_NOT_FOUND", message=f"Tool not configured: {tool_name}", retryable=False)
            self._logger.log(
                tool_name=tool_name,
                mode=self.mode,
                request_payload=payload,
                duration_ms=0,
                success=False,
                attempts=0,
                error_code=err.code,
                error_message=err.message,
            )
            raise err

        # Merge retry settings: options override take precedence over config
        max_retries = opts.retry_times if opts.retry_times > 1 else self._config.max_retries

        t0 = time.monotonic()
        attempt = 0
        last_error: AppError | None = None

        while attempt <= max_retries:
            attempt += 1
            try:
                result = await self._call_once(command, payload, opts.timeout_ms)
                elapsed = (time.monotonic() - t0) * 1000
                self._logger.log(
                    tool_name=tool_name,
                    mode=self.mode,
                    request_payload=payload if attempt == 1 else None,
                    duration_ms=elapsed,
                    success=True,
                    attempts=attempt,
                    response_result=result.result,
                )
                return result
            except AppError as exc:
                last_error = exc
                if not exc.retryable or attempt > max_retries:
                    elapsed = (time.monotonic() - t0) * 1000
                    self._logger.log(
                        tool_name=tool_name,
                        mode=self.mode,
                        request_payload=payload,
                        duration_ms=elapsed,
                        success=False,
                        attempts=attempt,
                        error_code=exc.code,
                        error_message=exc.message,
                    )
                    raise

                # Brief delay before retry
                await asyncio.sleep(self._config.retry_delay_ms / 1000)

        # Should be unreachable — the loop above always raises or returns
        assert last_error is not None
        raise last_error

    async def _call_once(self, command: str, payload: dict[str, Any], timeout_ms: int) -> BaseResponseModel:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
            env=os.environ.copy(),
        )
        raw_input = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(raw_input), timeout=timeout_ms / 1000)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise AppError(code="MCP_TIMEOUT", message=f"MCP call timed out: {command}", retryable=True)

        if proc.returncode not in (0, None):
            raise AppError(
                code="MCP_PROCESS_EXITED",
                message=f"MCP process exited with code {proc.returncode}",
                retryable=True,
                details={"stderr": stderr.decode('utf-8', errors='ignore')},
            )

        try:
            resp_payload = json.loads(stdout.decode("utf-8").strip() or "{}")
        except json.JSONDecodeError as exc:
            raise AppError(
                code="MCP_INVALID_RESPONSE",
                message="MCP response is not valid JSON",
                retryable=True,
                details={"error": str(exc), "stdout": stdout.decode('utf-8', errors='ignore')},
            ) from exc

        try:
            return BaseResponseModel.model_validate(resp_payload)
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                code="SCHEMA_VALIDATION_FAILED",
                message="MCP response failed schema validation",
                retryable=False,
                details={"error": str(exc)},
            ) from exc


class MockMcpClient(McpClient):
    def __init__(
        self,
        handlers: dict[str, BaseResponseModel],
        config: MCPConfig | None = None,
    ) -> None:
        super().__init__(config)
        self._handlers = handlers

    @property
    def mode(self) -> str:
        return "mock"

    async def call(self, tool_name: str, payload: dict[str, Any], options: McpCallOptions | None = None) -> BaseResponseModel:
        t0 = time.monotonic()
        try:
            result = self._handlers[tool_name]
            elapsed = (time.monotonic() - t0) * 1000
            self._logger.log(
                tool_name=tool_name,
                mode=self.mode,
                request_payload=payload,
                duration_ms=elapsed,
                success=True,
                attempts=1,
                response_result=result.result,
            )
            return result
        except KeyError as exc:
            elapsed = (time.monotonic() - t0) * 1000
            err = AppError(code="MCP_TOOL_NOT_FOUND", message=f"Mock tool not found: {tool_name}", retryable=False)
            self._logger.log(
                tool_name=tool_name,
                mode=self.mode,
                request_payload=payload,
                duration_ms=elapsed,
                success=False,
                attempts=1,
                error_code=err.code,
                error_message=err.message,
            )
            raise err from exc
