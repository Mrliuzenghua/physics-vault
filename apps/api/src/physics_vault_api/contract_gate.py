"""Automated checks that keep public API contracts from silently drifting."""

from __future__ import annotations

import ast
import argparse
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, get_args, get_origin

from fastapi.datastructures import DefaultPlaceholder
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from .application import ApplicationContainer
from .paths import project_root


@dataclass(frozen=True, slots=True)
class ContractViolation:
    code: str
    location: str
    message: str
    suggestion: str

    def __str__(self) -> str:
        return (
            f"[{self.code}] {self.location}\n"
            f"  problem: {self.message}\n"
            f"  fix: {self.suggestion}"
        )


# API-301 migrated every public map response to a named RootModel. Keep this
# empty: a new bare ``dict`` response is always a contract-gate violation.
BARE_DICT_RESPONSE_ALLOWLIST = frozenset()

_FETCH_CALL = re.compile(r"\bfetch\s*\(")


def _route_methods(route: APIRoute) -> tuple[str, ...]:
    return tuple(sorted(route.methods or ()))


def _is_json_response(route: APIRoute) -> bool:
    response_class = route.response_class
    if isinstance(response_class, DefaultPlaceholder):
        response_class = response_class.value
    return isinstance(response_class, type) and issubclass(response_class, JSONResponse)


def _is_bare_dictionary_response(response_model: object) -> bool:
    if response_model is dict:
        return True
    origin = get_origin(response_model)
    if origin is dict:
        return True
    return any(_is_bare_dictionary_response(argument) for argument in get_args(response_model))


def check_router_contracts(
    routes: Iterable[tuple[str, APIRoute]],
    *,
    bare_dict_allowlist: frozenset[tuple[str, str]] = BARE_DICT_RESPONSE_ALLOWLIST,
) -> list[ContractViolation]:
    """Validate route uniqueness and response contracts for a router manifest."""

    violations: list[ContractViolation] = []
    seen_paths: dict[tuple[str, str], str] = {}
    seen_operation_ids: dict[str, str] = {}

    for domain, route in routes:
        methods = _route_methods(route)
        location = f"{domain}:{','.join(methods)} {route.path}"
        for method in methods:
            key = (method, route.path)
            if previous := seen_paths.get(key):
                violations.append(ContractViolation(
                    "duplicate-route",
                    location,
                    f"duplicates {previous}",
                    "use a unique HTTP method and path, or remove the compatibility duplicate",
                ))
            else:
                seen_paths[key] = location

        for method in methods:
            operation_id = route.unique_id
            operation_location = f"{domain}:{method} {route.path}"
            if previous := seen_operation_ids.get(operation_id):
                violations.append(ContractViolation(
                    "duplicate-operation-id",
                    operation_location,
                    f"operation ID {operation_id!r} duplicates {previous}",
                    "set a unique operation_id for this public endpoint",
                ))
            else:
                seen_operation_ids[operation_id] = operation_location

        if not _is_json_response(route):
            continue
        if route.response_model is None:
            violations.append(ContractViolation(
                "missing-response-model",
                location,
                "JSON endpoint must declare a response_model",
                "declare a named response schema in the router decorator",
            ))
            continue
        if _is_bare_dictionary_response(route.response_model):
            for method in methods:
                if (method, route.path) not in bare_dict_allowlist:
                    violations.append(ContractViolation(
                        "bare-dict-response",
                        location,
                        "public JSON responses must use a named schema instead of dict",
                        "replace dict or list[dict] with a named response schema",
                    ))
    return violations


def _check_direct_fetches(root: Path) -> list[ContractViolation]:
    source_root = root / "apps" / "web" / "src"
    transport = source_root / "services" / "apiClient.ts"
    violations: list[ContractViolation] = []
    for path in source_root.rglob("*.ts*"):
        if path == transport:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _FETCH_CALL.search(line):
                violations.append(ContractViolation(
                    "direct-fetch",
                    f"{path.relative_to(root).as_posix()}:{line_number}",
                    "use services/apiClient.ts transport instead of fetch directly",
                    "move the request behind services/apiClient.ts and a typed domain client",
                ))
    return violations


def _tool_name(decorator: ast.expr, function_name: str) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if not (
        isinstance(target, ast.Attribute)
        and target.attr == "tool"
        and isinstance(target.value, ast.Name)
        and target.value.id == "server"
    ):
        return None
    if isinstance(decorator, ast.Call):
        for keyword in decorator.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                return keyword.value.value
    return function_name


def _check_mcp_tool_names(root: Path) -> list[ContractViolation]:
    source_path = root / "scripts" / "physics_vault_mcp_server.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8-sig"), filename=str(source_path))
    names: dict[str, int] = {}
    violations: list[ContractViolation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (name := _tool_name(decorator, node.name)) is None:
                continue
            if previous_line := names.get(name):
                violations.append(ContractViolation(
                    "duplicate-mcp-tool",
                    f"{source_path.relative_to(root).as_posix()}:{node.lineno}",
                    f"tool {name!r} already declared at line {previous_line}",
                    "rename the tool or remove the duplicate MCP registration",
                ))
            else:
                names[name] = node.lineno
    return violations


def check_project_contracts(root: Path | None = None) -> list[ContractViolation]:
    """Run every API-303 contract check against the current repository."""

    root = root or project_root()
    container = ApplicationContainer.build()
    router_routes = (
        (domain, route)
        for domain, router in container.router_manifest()
        for route in router.routes
        if isinstance(route, APIRoute)
    )
    violations = [
        *check_router_contracts(router_routes),
        *_check_direct_fetches(root),
        *_check_mcp_tool_names(root),
    ]
    return sorted(
        violations,
        key=lambda violation: (
            violation.code,
            violation.location,
            violation.message,
            violation.suggestion,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the reusable API-303 gate and return a CI-friendly process status."""

    parser = argparse.ArgumentParser(description="Check Physics Vault public API contracts.")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository root to inspect (defaults to the current Physics Vault project)",
    )
    args = parser.parse_args(argv)
    violations = check_project_contracts(args.root.resolve() if args.root else None)
    if not violations:
        print("API contract gate passed.")
        return 0
    print("API contract gate failed:")
    for violation in violations:
        print(f"- {violation}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
