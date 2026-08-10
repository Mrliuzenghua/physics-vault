from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from mcp_contracts.src.operation_plan import build_operation_plan
from physics_vault_api.repositories.operation_plans import OperationPlanRepository
from physics_vault_api.services.operation_plans import OperationPlanService, OperationPlanVersionConflict


def _service(tmp_path) -> OperationPlanService:
    return OperationPlanService(OperationPlanRepository(tmp_path / "operation-plans.sqlite3"))


def _plan(**overrides):
    plan = build_operation_plan(
        action="assets.cleanup",
        targets=[{"type": "asset", "id": "asset-1"}],
        summary="clean one asset",
        version_snapshot={"asset": "asset-1", "revision": 1},
        reversible=False,
    )
    return plan.model_copy(update=overrides)


def test_preview_is_persisted_with_expiry_and_initial_state(tmp_path) -> None:
    service = _service(tmp_path)
    plan = _plan()

    saved = service.save_preview(plan)

    assert saved.plan.operation_id == plan.operation_id
    assert saved.status == "planned"
    assert saved.plan.expires_at > datetime.now(timezone.utc)


def test_completed_plan_replays_its_result_without_reexecuting(tmp_path) -> None:
    service = _service(tmp_path)
    plan = _plan()
    service.save_preview(plan)
    calls = 0

    def execute(_plan):
        nonlocal calls
        calls += 1
        return {"deleted": 1}

    first = service.execute(plan.operation_id, version_reader=lambda item: item.expected_version or "", executor=execute)
    replay = service.execute(plan.operation_id, version_reader=lambda item: item.expected_version or "", executor=execute)

    assert first.status == "completed"
    assert replay.status == "completed"
    assert replay.idempotent is True
    assert replay.result == {"deleted": 1}
    assert calls == 1


def test_version_conflict_keeps_preview_planned_and_does_not_execute(tmp_path) -> None:
    service = _service(tmp_path)
    plan = _plan()
    service.save_preview(plan)

    with pytest.raises(OperationPlanVersionConflict):
        service.execute(plan.operation_id, version_reader=lambda _plan: "newer-version", executor=lambda _plan: None)

    assert service._repository.get(plan.operation_id).status == "planned"


def test_expired_plan_is_not_executed(tmp_path) -> None:
    service = _service(tmp_path)
    plan = _plan(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    service.save_preview(plan)

    result = service.execute(plan.operation_id, executor=lambda _plan: pytest.fail("must not execute"))

    assert result.status == "expired"


def test_failure_is_recorded_and_never_marked_completed(tmp_path) -> None:
    service = _service(tmp_path)
    plan = _plan()
    service.save_preview(plan)

    result = service.execute(plan.operation_id, executor=lambda _plan: (_ for _ in ()).throw(ValueError("write failed")))

    assert result.status == "failed"
    assert result.error == "write failed"
    assert service._repository.get(plan.operation_id).status == "failed"


def test_concurrent_claim_allows_only_one_executor(tmp_path) -> None:
    service = _service(tmp_path)
    plan = _plan()
    service.save_preview(plan)
    calls = 0
    call_lock = threading.Lock()
    start = threading.Barrier(2)
    results = []

    def executor(_plan):
        nonlocal calls
        with call_lock:
            calls += 1
        time.sleep(0.05)
        return {"ok": True}

    def run() -> None:
        start.wait()
        results.append(service.execute(plan.operation_id, executor=executor))

    threads = [threading.Thread(target=run), threading.Thread(target=run)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == 1
    assert service._repository.get(plan.operation_id).status == "completed"
    assert {result.status for result in results} <= {"executing", "completed"}
