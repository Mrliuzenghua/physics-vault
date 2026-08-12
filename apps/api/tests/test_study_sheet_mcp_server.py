from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERVER_PATH = PROJECT_ROOT / "scripts" / "study_sheet_mcp_server.mjs"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resource_root(tmp_path: Path) -> Path:
    root = tmp_path / "教学资源库"
    templates = root / "01-模板"
    output = root / "02-知识讲义"
    templates.mkdir(parents=True)
    output.mkdir()
    template = templates / "knowledge.typ"
    template.write_text(
        '#let topic = "示例"\n#set document(date: none)\n= #topic\n',
        encoding="utf-8",
    )
    (templates / "教学PPT模板-物理题HTML.html").write_text(
        """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>模板</title>
<style>.question-choice{}.question-experiment{}.question-calculation{} body.answers-hidden .analysis-overlay{opacity:0}</style>
<script>window.MathJax = {};</script><script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
</head><body><main class="deck"><section class="slide">模板页</section></main>
<div class="deck-controls"><button id="toggle-answer">显示答案</button><div class="deck-indicator" id="deck-indicator">1 / 1</div></div>
<script>const slides = Array.from(document.querySelectorAll('.slide'));</script></body></html>
""",
        encoding="utf-8",
    )
    (templates / "教学PPT模板-物理题Typst.typ").write_text(
        (PROJECT_ROOT / "scripts" / "templates" / "physics_typst_presentation.typ").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    registry = {
        "templates": [
            {
                "id": "knowledge-handout",
                "name": "知识讲义",
                "template_file": template.name,
                "template_sha256": _sha256(template),
                "output_dir": "02-知识讲义",
                "filename_pattern": "{seq}-{topic}.typ",
                "required_fields": ["topic"],
                "editable_sections": ["document-content"],
            }
        ]
    }
    (templates / "templates.json").write_text(
        json.dumps(registry, ensure_ascii=False), encoding="utf-8"
    )
    return root


def _rpc(root: Path, calls: list[dict[str, object]]) -> list[dict[str, object]]:
    payload = "\n".join(json.dumps(call, ensure_ascii=False) for call in calls) + "\n"
    env = {**os.environ, "PHYSICS_STUDY_SHEET_ROOT": str(root)}
    result = subprocess.run(
        ["node", str(SERVER_PATH)],
        input=payload,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=PROJECT_ROOT,
        timeout=15,
        check=True,
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _call(tool: str, arguments: dict[str, object], request_id: int = 1) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }


def _content(response: dict[str, object]) -> dict[str, object]:
    result = response["result"]
    assert isinstance(result, dict)
    blocks = result["content"]
    assert isinstance(blocks, list)
    return json.loads(blocks[0]["text"])


def test_lists_expected_tools_and_audits_templates(tmp_path: Path) -> None:
    root = _resource_root(tmp_path)
    responses = _rpc(
        root,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            _call("audit_study_sheet_templates", {}, 2),
        ],
    )

    tools = responses[0]["result"]["tools"]
    assert {item["name"] for item in tools} == {
        "get_study_sheet_root_status",
        "list_study_sheet_templates",
        "create_study_sheet",
        "validate_and_compile_study_sheet",
        "audit_study_sheet_templates",
        "get_html_presentation_template",
        "create_html_presentation",
        "validate_html_presentation",
        "audit_html_presentation_template",
        "get_typst_presentation_template",
        "create_typst_presentation",
        "validate_typst_presentation",
        "audit_typst_presentation_template",
    }
    assert _content(responses[1])["checks"][0]["passed"] is True


def test_dry_run_does_not_write_and_real_calls_increment_sequence(tmp_path: Path) -> None:
    root = _resource_root(tmp_path)
    arguments = {
        "template_id": "knowledge-handout",
        "topic": "匀变速直线运动",
        "typst_body": "正文",
        "dry_run": True,
    }
    preview = _content(_rpc(root, [_call("create_study_sheet", arguments)])[0])
    output = root / "02-知识讲义"
    assert preview["status"] == "preview"
    assert list(output.iterdir()) == []

    arguments["dry_run"] = False
    first = _content(_rpc(root, [_call("create_study_sheet", arguments)])[0])
    second = _content(_rpc(root, [_call("create_study_sheet", arguments)])[0])
    assert Path(first["source_path"]).name.startswith("001-")
    assert Path(second["source_path"]).name.startswith("002-")
    assert len(list(output.glob("*.typ"))) == 2


def test_operation_id_makes_creation_idempotent_and_rejects_payload_conflict(tmp_path: Path) -> None:
    root = _resource_root(tmp_path)
    arguments = {
        "template_id": "knowledge-handout",
        "topic": "动量守恒",
        "typst_body": "正文",
        "operation_id": "lesson-momentum-001",
    }
    first = _content(_rpc(root, [_call("create_study_sheet", arguments)])[0])
    replay = _content(_rpc(root, [_call("create_study_sheet", arguments)])[0])

    assert first["status"] == "created"
    assert replay["status"] == "existing"
    assert replay["idempotent"] is True
    assert replay["source_path"] == first["source_path"]
    assert len(list((root / "02-知识讲义").glob("*.typ"))) == 1

    conflict_arguments = {**arguments, "typst_body": "不同正文"}
    conflict = _rpc(root, [_call("create_study_sheet", conflict_arguments)])[0]
    assert "error" in conflict
    assert "operation_id" in conflict["error"]["message"]


def test_rejects_paths_outside_managed_output(tmp_path: Path) -> None:
    root = _resource_root(tmp_path)
    outside = tmp_path / "outside.typ"
    outside.write_text("// Generated by Physics Vault study-sheet-workflow.\n", encoding="utf-8")
    response = _rpc(
        root,
        [_call("validate_and_compile_study_sheet", {
            "template_id": "knowledge-handout",
            "source_path": str(outside),
            "compile": False,
        })],
    )[0]
    assert "error" in response
    assert "source_path" in response["error"]["message"]


def test_existing_pdf_requires_explicit_overwrite(tmp_path: Path) -> None:
    root = _resource_root(tmp_path)
    output = root / "02-知识讲义"
    source = output / "001-test.typ"
    source.write_text(
        "// Generated by Physics Vault study-sheet-workflow.\n#set document(date: none)\nTest\n",
        encoding="utf-8",
    )
    pdf = source.with_suffix(".pdf")
    pdf.write_bytes(b"existing")

    result = _content(_rpc(
        root,
        [_call("validate_and_compile_study_sheet", {
            "template_id": "knowledge-handout",
            "source_path": str(source),
        })],
    )[0])
    assert result["status"] == "pdf_exists"
    assert result["overwrite_required"] is True
    assert pdf.read_bytes() == b"existing"


def test_template_hash_mismatch_is_reported(tmp_path: Path) -> None:
    root = _resource_root(tmp_path)
    template = root / "01-模板" / "knowledge.typ"
    template.write_text("changed", encoding="utf-8")

    audit = _content(_rpc(root, [_call("audit_study_sheet_templates", {})])[0])
    assert audit["checks"][0]["passed"] is False


def test_html_presentation_dry_run_create_and_validate(tmp_path: Path) -> None:
    root = _resource_root(tmp_path)
    image = root / "02-知识讲义" / "题图.png"
    image.write_bytes(b"image")
    arguments = {
        "title": "匀变速直线运动",
        "subtitle": "课堂例题精讲",
        "teacher": "李老师",
        "chapter": "运动学",
        "questions": [
            {
                "question_type": "single_choice",
                "section": "基础辨析",
                "title": "速度与加速度",
                "source": "校本题",
                "stem": "物体做匀加速直线运动，$v=v_0+at$。",
                "choices": ["速度一定增大", "加速度保持不变"],
                "answer": "B",
                "analysis": ["先明确加速度恒定。", "$v=v_0+at$"],
                "keypoint": "注意速度方向。",
                "image_paths": [str(image)],
            }
        ],
        "operation_id": "html-deck-001",
        "dry_run": True,
    }
    preview = _content(_rpc(root, [_call("create_html_presentation", arguments)])[0])
    output = root / "05-课堂PPT"
    assert preview["status"] == "preview"
    assert preview["page_count"] == 4
    assert not output.exists()

    arguments["dry_run"] = False
    created = _content(_rpc(root, [_call("create_html_presentation", arguments)])[0])
    source = Path(created["source_path"])
    assert created["status"] == "created"
    assert source.exists()
    body = source.read_text(encoding="utf-8")
    assert "匀变速直线运动" in body
    assert "Physics Vault html-presentation-workflow" in body
    assert "{{" not in body
    assert len(list((output / "images").glob("*.png"))) == 1

    validated = _content(_rpc(root, [_call("validate_html_presentation", {"source_path": str(source)})])[0])
    assert validated["status"] == "validated"
    assert validated["slide_count"] == 4
    assert validated["question_count"] == 1


def test_html_presentation_escapes_markup_and_operation_id_is_idempotent(tmp_path: Path) -> None:
    root = _resource_root(tmp_path)
    arguments = {
        "title": "动量守恒",
        "questions": [{"stem": "<script>alert(1)</script>，且 $p=mv$", "answer": "守恒"}],
        "operation_id": "html-momentum-001",
    }
    first = _content(_rpc(root, [_call("create_html_presentation", arguments)])[0])
    replay = _content(_rpc(root, [_call("create_html_presentation", arguments)])[0])
    body = Path(first["source_path"]).read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<script>alert(1)</script>" not in body
    assert replay["status"] == "existing"
    assert replay["source_path"] == first["source_path"]


def test_typst_presentation_dry_run_create_validate_and_replay(tmp_path: Path) -> None:
    root = _resource_root(tmp_path)
    arguments = {
        "title": "动量守恒",
        "subtitle": "课堂题目与解析",
        "questions": [
            {
                "question_type": "calculation",
                "title": "完全非弹性碰撞",
                "stem": "质量分别为 $m_1$、$m_2$ 的两物体碰撞后粘在一起。",
                "data_items": ["$m_1=1\\,\\text{kg}$", "$m_2=2\\,\\text{kg}$"],
                "prompt": "求共同速度。",
                "answer": "$v=2\\,\\text{m/s}$",
                "analysis": ["选择两物体组成的系统。", "$m_1v_1+m_2v_2=(m_1+m_2)v$"],
                "keypoint": "先规定正方向。",
            }
        ],
        "operation_id": "typst-momentum-001",
        "dry_run": True,
    }
    preview = _content(_rpc(root, [_call("create_typst_presentation", arguments)])[0])
    assert preview["status"] == "preview"
    assert preview["slide_count"] == 4
    assert not (root / "05-课堂PPT").exists()

    arguments["dry_run"] = False
    created = _content(_rpc(root, [_call("create_typst_presentation", arguments)])[0])
    source = Path(created["source_path"])
    pdf = Path(created["pdf_path"])
    assert created["status"] == "created"
    assert source.name.endswith("-TYPST.typ")
    assert pdf.name.endswith("-TYPST.pdf")
    assert source.exists()
    assert pdf.read_bytes().startswith(b"%PDF")
    assert Path(f"{source}.manifest.json").exists()
    body = source.read_text(encoding="utf-8")
    assert "Physics Vault typst-presentation-workflow" in body
    assert "m_1" in body
    assert "m_1 v_1" in body
    assert "{{GENERATED_CONTENT}}" not in body

    replay = _content(_rpc(root, [_call("create_typst_presentation", arguments)])[0])
    assert replay["status"] == "existing"
    assert replay["source_path"] == created["source_path"]

    validated = _content(_rpc(root, [_call("validate_typst_presentation", {"source_path": str(source)})])[0])
    assert validated["status"] == "validated"
    assert validated["slide_count"] == 4
    assert validated["errors"] == []
