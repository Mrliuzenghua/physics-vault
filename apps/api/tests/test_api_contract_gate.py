from __future__ import annotations

from fastapi import APIRouter
from fastapi.routing import APIRoute

from physics_vault_api.contract_gate import check_project_contracts, check_router_contracts, main


def test_api_contract_gate_passes_for_the_project() -> None:
    assert check_project_contracts() == []


def test_router_contract_gate_detects_duplicate_routes_and_bare_dict_responses() -> None:
    router = APIRouter()

    @router.get("/duplicate")
    def first() -> dict[str, str]:
        return {"value": "one"}

    @router.get("/duplicate")
    def second() -> dict[str, str]:
        return {"value": "two"}

    routes = [("fixture", route) for route in router.routes if isinstance(route, APIRoute)]
    codes = {violation.code for violation in check_router_contracts(routes, bare_dict_allowlist=frozenset())}

    assert "duplicate-route" in codes
    assert "bare-dict-response" in codes


def test_router_contract_gate_detects_plain_and_nested_bare_dict_models() -> None:
    router = APIRouter()

    @router.get("/plain", response_model=dict)
    def plain() -> dict:
        return {}

    @router.get("/nested", response_model=list[dict])
    def nested() -> list[dict]:
        return []

    routes = [("fixture", route) for route in router.routes if isinstance(route, APIRoute)]
    violations = check_router_contracts(routes, bare_dict_allowlist=frozenset())

    bare_locations = {item.location for item in violations if item.code == "bare-dict-response"}
    assert bare_locations == {"fixture:GET /plain", "fixture:GET /nested"}


def test_contract_gate_cli_reports_fixture_location_suggestion_and_failure_exit_code(tmp_path, capsys) -> None:
    fixture = tmp_path / "apps" / "web" / "src" / "fixtures" / "directFetchFixture.ts"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(
        "export async function loadFixture() {\n"
        "  return fetch('/api/fixture');\n"
        "}\n",
        encoding="utf-8",
    )
    mcp_server = tmp_path / "scripts" / "physics_vault_mcp_server.py"
    mcp_server.parent.mkdir(parents=True)
    mcp_server.write_text("server = object()\n", encoding="utf-8")

    assert main(["--root", str(tmp_path)]) == 1

    output = capsys.readouterr().out
    assert "[direct-fetch] apps/web/src/fixtures/directFetchFixture.ts:2" in output
    assert "fix: move the request behind services/apiClient.ts and a typed domain client" in output
