"""Persistent, validated Word export format templates."""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..paths import project_root

FORMAT_SCHEMA = "physics-vault/word-export-format/v1"
_TEMPLATE_FILE = project_root() / "data" / "config" / "word_export_templates.json"
_HEX_COLOR = re.compile(r"^[0-9A-Fa-f]{6}$")
_ALIGNMENTS = {"left", "center", "right", "justify"}

DEFAULT_STYLE_CONFIG: dict[str, Any] = {
    "fontFamily": "songti",
    "fontSize": 10.5,
    "lineHeight": 1.55,
    "paragraphSpacing": 4,
    "questionSpacing": 10,
    "figureScale": 60,
    "pageMarginTop": 18,
    "pageMarginBottom": 18,
    "pageMarginLeft": 20,
    "pageMarginRight": 20,
    "questionNumberStyle": "decimal",
    "pageSize": "A4",
    "pageOrientation": "portrait",
    "layoutMode": "flow",
    "optionLayout": "auto",
    "keepQuestionTogether": True,
    "keepFigureWithStem": True,
    "startLongQuestionOnNewPage": True,
    "pageFillPercent": 90,
}

DEFAULT_HEADER_FOOTER: dict[str, Any] = {
    "headerEnabled": False,
    "headerText": "",
    "headerAlign": "center",
    "footerEnabled": False,
    "footerText": "",
    "footerAlign": "center",
    "showPageNumber": True,
}

DEFAULT_CONTENT_STYLES: dict[str, dict[str, Any]] = {
    "documentTitle": {"fontFamily": "heiti", "fontSize": 16, "bold": True, "textAlign": "center", "spaceAfter": 8},
    "sectionTitle": {"fontFamily": "heiti", "fontSize": 14, "bold": True, "spaceBefore": 10, "spaceAfter": 6},
    "questionNumber": {"fontFamily": "songti", "fontSize": 10.5, "bold": False},
    "questionStem": {"fontFamily": "songti", "fontSize": 10.5, "spaceAfter": 4, "keepWithNext": True},
    "options": {"fontFamily": "songti", "fontSize": 10.5, "spaceAfter": 2, "optionLayout": "auto"},
    "answer": {"fontFamily": "kaiti", "fontSize": 10.5, "color": "000000", "spaceBefore": 4},
    "analysis": {"fontFamily": "kaiti", "fontSize": 10.5, "color": "000000", "spaceBefore": 2},
    "knowledgeTitle": {"fontFamily": "heiti", "fontSize": 14, "bold": True, "spaceBefore": 10, "spaceAfter": 4},
    "knowledgeBody": {"fontFamily": "songti", "fontSize": 10.5, "spaceAfter": 4},
    "figureCaption": {"fontFamily": "songti", "fontSize": 9, "italic": True, "textAlign": "center"},
}

DEFAULT_FORMAT_SPEC: dict[str, Any] = {
    "schema": FORMAT_SCHEMA,
    "name": "标准试卷",
    "description": "A4 纵向、适合正式试卷的基础 Word 排版。",
    "styleConfig": DEFAULT_STYLE_CONFIG,
    "headerFooter": DEFAULT_HEADER_FOOTER,
    "contentStyles": DEFAULT_CONTENT_STYLES,
    "rules": [],
    "output": {
        "includeAnswers": False,
        "includeAnalysis": False,
        "answerPosition": "after_question",
    },
}

DEFAULT_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "formal_exam",
        "name": "正式试卷",
        "description": "A4 纵向，题干与选项紧凑，适合打印考试。",
        "builtIn": True,
        "formatSpec": DEFAULT_FORMAT_SPEC,
    },
    {
        "id": "student_practice",
        "name": "学生练习册",
        "description": "保留较宽松的题间距，默认隐藏答案和解析。",
        "builtIn": True,
        "formatSpec": {
            **DEFAULT_FORMAT_SPEC,
            "name": "学生练习册",
            "styleConfig": {**DEFAULT_STYLE_CONFIG, "fontSize": 12, "lineHeight": 1.7, "questionSpacing": 16, "pageFillPercent": 86},
        },
    },
    {
        "id": "teacher_handout",
        "name": "教师讲义",
        "description": "显示答案和解析，答案使用楷体区分。",
        "builtIn": True,
        "formatSpec": {
            **DEFAULT_FORMAT_SPEC,
            "name": "教师讲义",
            "output": {"includeAnswers": True, "includeAnalysis": True, "answerPosition": "after_question"},
            "styleConfig": {**DEFAULT_STYLE_CONFIG, "fontSize": 11, "lineHeight": 1.7, "questionSpacing": 14},
        },
    },
]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def normalize_format_spec(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    value = _deep_merge(DEFAULT_FORMAT_SPEC, raw or {})
    value["schema"] = FORMAT_SCHEMA
    value["styleConfig"] = _deep_merge(DEFAULT_STYLE_CONFIG, value.get("styleConfig") or {})
    value["headerFooter"] = _deep_merge(DEFAULT_HEADER_FOOTER, value.get("headerFooter") or {})
    value["contentStyles"] = _deep_merge(DEFAULT_CONTENT_STYLES, value.get("contentStyles") or {})
    value["rules"] = value.get("rules") if isinstance(value.get("rules"), list) else []
    value["output"] = _deep_merge(DEFAULT_FORMAT_SPEC["output"], value.get("output") or {})
    return value


def validate_format_spec(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"ok": False, "errors": ["format_spec 必须是对象"], "warnings": [], "formatSpec": normalize_format_spec()}

    spec = normalize_format_spec(raw)
    errors: list[str] = []
    warnings: list[str] = []
    style = spec["styleConfig"]
    if style.get("pageSize") not in {"A4", "A3"}:
        errors.append("styleConfig.pageSize 必须是 A4 或 A3")
    if style.get("pageOrientation") not in {"portrait", "landscape"}:
        errors.append("styleConfig.pageOrientation 必须是 portrait 或 landscape")
    if style.get("optionLayout") not in {"auto", "single", "double"}:
        errors.append("styleConfig.optionLayout 必须是 auto、single 或 double")
    for key in ("fontSize", "lineHeight", "paragraphSpacing", "questionSpacing", "figureScale", "pageFillPercent"):
        try:
            if float(style[key]) <= 0:
                errors.append(f"styleConfig.{key} 必须大于 0")
        except (TypeError, ValueError):
            errors.append(f"styleConfig.{key} 必须是数字")
    if float(style.get("figureScale", 60)) > 100:
        warnings.append("styleConfig.figureScale 超过 100，导出时会限制到可用宽度")
    if spec["output"].get("answerPosition") not in {"after_question", "end"}:
        errors.append("output.answerPosition 必须是 after_question 或 end")
    for name, content_style in spec["contentStyles"].items():
        if not isinstance(content_style, dict):
            errors.append(f"contentStyles.{name} 必须是对象")
            continue
        if "textAlign" in content_style and content_style["textAlign"] not in _ALIGNMENTS:
            errors.append(f"contentStyles.{name}.textAlign 对齐方式无效")
        if "color" in content_style and not _HEX_COLOR.fullmatch(str(content_style["color"])):
            errors.append(f"contentStyles.{name}.color 必须是六位十六进制颜色")
        if "fontSize" in content_style:
            try:
                if float(content_style["fontSize"]) <= 0:
                    errors.append(f"contentStyles.{name}.fontSize 必须大于 0")
            except (TypeError, ValueError):
                errors.append(f"contentStyles.{name}.fontSize 必须是数字")
    if not isinstance(spec["rules"], list):
        errors.append("rules 必须是数组")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "formatSpec": spec}


def _read_user_templates() -> list[dict[str, Any]]:
    if not _TEMPLATE_FILE.is_file():
        return []
    try:
        data = json.loads(_TEMPLATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _write_user_templates(templates: list[dict[str, Any]]) -> None:
    _TEMPLATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = _TEMPLATE_FILE.with_suffix(f".{uuid4().hex}.tmp")
    temp.write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, _TEMPLATE_FILE)


def list_word_export_templates() -> list[dict[str, Any]]:
    templates = deepcopy(DEFAULT_TEMPLATES)
    for item in _read_user_templates():
        if not isinstance(item, dict) or not item.get("id"):
            continue
        normalized = {**item, "builtIn": False, "formatSpec": normalize_format_spec(item.get("formatSpec"))}
        index = next((i for i, current in enumerate(templates) if current["id"] == normalized["id"]), None)
        if index is None:
            templates.append(normalized)
        else:
            templates[index] = normalized
    return templates


def get_word_export_template(template_id: str) -> dict[str, Any] | None:
    return next((item for item in list_word_export_templates() if item["id"] == template_id), None)


def save_word_export_template(
    name: str,
    format_spec: dict[str, Any],
    *,
    template_id: str | None = None,
    description: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    checked = validate_format_spec(format_spec)
    if not checked["ok"]:
        return {"ok": False, "errors": checked["errors"], "warnings": checked["warnings"]}
    clean_name = str(name or "").strip()
    if not clean_name:
        return {"ok": False, "errors": ["模板名称不能为空"], "warnings": []}
    current = _read_user_templates()
    existing_id = str(template_id or "").strip()
    if existing_id and any(item.get("id") == existing_id and item.get("builtIn") for item in DEFAULT_TEMPLATES):
        return {"ok": False, "errors": ["内置模板不能覆盖，请另存为新模板"], "warnings": []}
    index = next((i for i, item in enumerate(current) if item.get("id") == existing_id), None) if existing_id else None
    if index is not None and not overwrite:
        return {"ok": False, "errors": ["模板已存在，请设置 overwrite=true"], "warnings": []}
    now = datetime.now(UTC).isoformat()
    item = {
        "id": existing_id or f"custom-{uuid4().hex[:12]}",
        "name": clean_name,
        "description": str(description or checked["formatSpec"].get("description") or "").strip(),
        "builtIn": False,
        "createdAt": current[index].get("createdAt", now) if index is not None else now,
        "updatedAt": now,
        "formatSpec": {**checked["formatSpec"], "name": clean_name},
    }
    if index is None:
        current.append(item)
    else:
        current[index] = item
    _write_user_templates(current)
    return {"ok": True, "template": item, "warnings": checked["warnings"]}


def rename_word_export_template(template_id: str, name: str) -> dict[str, Any]:
    template = get_word_export_template(template_id)
    if not template:
        return {"ok": False, "errors": [f"找不到模板: {template_id}"]}
    if template.get("builtIn"):
        return {"ok": False, "errors": ["内置模板不能重命名"]}
    clean_name = str(name or "").strip()
    if not clean_name:
        return {"ok": False, "errors": ["模板名称不能为空"]}
    current = _read_user_templates()
    for item in current:
        if item.get("id") == template_id:
            item["name"] = clean_name
            item["updatedAt"] = datetime.now(UTC).isoformat()
            item["formatSpec"] = {**normalize_format_spec(item.get("formatSpec")), "name": clean_name}
            _write_user_templates(current)
            return {"ok": True, "template": item}
    return {"ok": False, "errors": [f"找不到可编辑模板: {template_id}"]}


def format_spec_for_template(template_id: str | None, override: dict[str, Any] | None = None) -> dict[str, Any]:
    base = get_word_export_template(template_id) if template_id else None
    source = base.get("formatSpec") if base else None
    return normalize_format_spec(_deep_merge(source or {}, override or {}))
