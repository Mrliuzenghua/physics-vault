from __future__ import annotations

from fastapi import APIRouter
from fastapi.routing import APIRoute

from physics_vault_api.contract_gate import check_project_contracts, check_router_contracts


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
