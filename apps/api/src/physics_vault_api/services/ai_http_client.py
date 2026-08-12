"""
Lightweight OpenAI-compatible HTTP client for AI tasks.

Used by McpGatewayService when the frontend has pushed runtime
configuration (base_url + api_key + model_name) via the
POST /api/mcp/config endpoint.

Supports both LLM (text) and VL (vision) calls through the
standard /chat/completions endpoint.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AiHttpClient:
    """Calls an OpenAI-compatible chat completions API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: int = 120,
        max_retries: int = 3,
    ) -> None:
        import urllib.request
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model_name
        self._timeout = timeout_seconds
        self._max_retries = max_retries

    # ── Low-level call ────────────────────────────────────────────

    def _call(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
        model_name: str | None = None,
        thinking: str | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request and return the parsed JSON response."""
        import http.client
        import urllib.request
        import urllib.error

        effective_timeout = timeout_seconds if timeout_seconds is not None else self._timeout

        # Normalize base_url: strip trailing slash, handle common formats
        base = self._base_url.rstrip("/")
        # If base_url already ends with /chat/completions or /v1, don't double-add
        if base.endswith("/chat/completions"):
            url = base
        elif base.endswith("/v1"):
            url = f"{base}/chat/completions"
        else:
            url = f"{base}/chat/completions"

        body: dict[str, Any] = {
            "model": model_name or self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            body["response_format"] = response_format
        if thinking is not None:
            body["thinking"] = {"type": thinking}

        def _do_request(payload_bytes: bytes) -> dict[str, Any]:
            req = urllib.request.Request(
                url,
                data=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            choice = raw.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            return self._parse_content(content)

        last_error: Exception | None = None
        last_body: str = ""
        for attempt in range(self._max_retries):
            try:
                payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
                return _do_request(payload)
            except urllib.error.HTTPError as exc:
                last_error = exc
                last_body = exc.read().decode("utf-8", errors="replace")
                logger.warning(
                    "AI HTTP call attempt %d/%d to %s failed: HTTP %s — %s",
                    attempt + 1, self._max_retries, url, exc.code, last_body[:500],
                )
                # On 400, retry without response_format (some providers reject it)
                if exc.code == 400 and body.get("response_format"):
                    body.pop("response_format", None)
                    logger.info("Retrying without response_format field")
                    continue
                if exc.code in (401, 403):
                    raise RuntimeError(
                        f"AI API 认证失败 (HTTP {exc.code})：请检查 API Key 是否正确。\n"
                        f"目标 URL: {url}\n模型: {self._model}\n响应: {last_body[:300]}"
                    ) from exc
            except Exception as exc:
                last_error = exc
                last_body = str(exc)
                logger.warning(
                    "AI HTTP call attempt %d/%d to %s failed: %s",
                    attempt + 1, self._max_retries, url, exc,
                )

        raise RuntimeError(
            f"AI API 调用失败（已重试 {self._max_retries} 次）\n"
            f"目标 URL: {url}\n模型: {self._model}\n"
            f"最后错误: {last_error}\n响应: {last_body[:500]}"
        )

    @staticmethod
    def _parse_content(content: str) -> dict[str, Any]:
        """Try to parse content as JSON, fall back to wrapping in a dict."""
        if not content:
            return {"text": ""}
        import re as _re

        text = content.strip()
        # Strip reasoning-model thinking blocks (<think>...</think>) — they
        # precede the actual answer and break JSON parsing.
        text = _re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        # Strip markdown code fences if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
            return {"text": text}
        except json.JSONDecodeError:
            # Last resort: extract the outermost {...} JSON object from the text
            match = _re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
            array_match = _re.search(r"\[[\s\S]*\]", text)
            if array_match:
                try:
                    parsed = json.loads(array_match.group(0))
                    if isinstance(parsed, list):
                        return {"items": parsed}
                except json.JSONDecodeError:
                    pass
            return {"text": content.strip()}

    # ── High-level AI task helpers ─────────────────────────────────

    def generate_analysis(
        self,
        question: dict[str, Any],
        style: str = "classroom_brief",
        include_extension: bool = False,
    ) -> dict[str, Any]:
        """Generate only the answer and analysis for a physics question."""
        # Build a rich text description from all available fields
        parts: list[str] = []
        title = str(question.get("title", "")).strip()
        if title:
            parts.append(f"【题目】{title}")
        options = question.get("options", [])
        if isinstance(options, list) and len(options) > 0:
            opt_text = "  ".join(
                f"{o.get('opt', '')}. {o.get('content', '')}" if isinstance(o, dict) else str(o)
                for o in options
            )
            if opt_text.strip():
                parts.append(f"【选项】{opt_text}")
        answer = str(question.get("answer", "")).strip()
        if answer:
            parts.append(f"【答案】{answer}")
        analysis = str(question.get("analysis", "")).strip()
        if analysis:
            parts.append(f"【已有解析】{analysis}")
        kp = str(question.get("knowledge_point", "")).strip()
        if kp:
            parts.append(f"【知识点】{kp}")

        if not parts:
            parts.append(json.dumps(question, ensure_ascii=False))

        question_text = "\n\n".join(parts)

        system_prompt = """你是一位资深高中物理教师。请解答题目，只生成答案和解析，不要改写题干，不要补充题型、难度、知识点、标签、来源或选项。

严格返回合法 JSON，不要添加 Markdown 代码块：
{"answer":"最终答案","analysis":"考试标准格式的解析"}

要求：
1. answer 只写最终答案；选择题写选项字母，填空题写结果，计算题写最终结论。
2. analysis 给出必要的物理依据、公式和推导，使用自然中文，公式使用 LaTeX。
3. 只根据下方提供的文字作答。系统不会向你提供或识别题目图片；如果缺少图片内容导致无法确定答案，不得猜测，answer 返回“信息不足”，analysis 简要说明缺少哪项图示信息。
4. 不输出上述两个字段之外的内容。"""

        if style == "classroom_brief":
            extra = "\n请生成课堂教学用的简要解析（150-300字）。"
        elif style == "self_study_full":
            extra = "\n请生成自习用的详尽解析（500字以上）。"
        elif style == "exam_standard":
            extra = "\n请生成考试标准答案格式的解析。"
        else:
            extra = ""

        # Answer completion is an interactive editing action, so prefer the
        # lower-latency Flash model on the official DeepSeek V4 endpoint. Keep
        # custom OpenAI-compatible providers on the explicitly configured model.
        analysis_model = self._model
        analysis_thinking: str | None = None
        if self._base_url.rstrip("/") == "https://api.deepseek.com":
            if self._model == "deepseek-v4-pro":
                analysis_model = "deepseek-v4-flash"
            analysis_thinking = "disabled"

        max_tokens_by_style = {
            "classroom_brief": 1200,
            "exam_standard": 1600,
            "self_study_full": 2600,
        }
        return self._call(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question_text + extra},
            ],
            temperature=0.2,
            max_tokens=max_tokens_by_style.get(style, 1600),
            response_format={"type": "json_object"},
            timeout_seconds=min(60, self._timeout),
            model_name=analysis_model,
            thinking=analysis_thinking,
        )

    def generate_knowledge(
        self,
        knowledge_points: list[str],
        style: str = "",
        length: str = "medium",
        include_formula: bool = True,
        include_common_mistakes: bool = True,
    ) -> dict[str, Any]:
        """Generate knowledge point topical content."""
        kp_list = "\n".join(f"- {kp}" for kp in knowledge_points)
        length_guide = {"short": "500字以内", "medium": "1000-2000字", "long": "3000字以上"}.get(length, "1000-2000字")
        system_prompt = (
            f"你是一位高中物理教育专家。请根据以下知识点生成教学内容。"
            f"长度要求：{length_guide}。"
            f"{'请包含关键公式。' if include_formula else ''}"
            f"{'请包含常见错误分析。' if include_common_mistakes else ''}"
            "请以 JSON 格式输出：{\"title\": \"...\", \"content\": \"...\", \"outline\": [\"...\"]}"
        )
        return self._call([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": kp_list},
        ], temperature=0.5, max_tokens=4096)

    def generate_metadata(
        self,
        questions: list[dict[str, Any]],
        fields: list[str],
        only_fill_empty: bool = True,
    ) -> dict[str, Any]:
        """Batch generate metadata (knowledge_points, tags, source) for questions."""
        q_json = json.dumps(questions, ensure_ascii=False, indent=2)
        fields_str = "、".join(fields)
        system_prompt = (
            f"你是一位高中物理题库管理员。请为每道题目补全以下字段：{fields_str}。"
            f"{'只填充空字段。' if only_fill_empty else '覆盖已有字段。'}"
            "请以 JSON 数组格式输出，每项包含 question_id 和更新的字段值。"
        )
        return self._call([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": q_json},
        ], temperature=0.2, max_tokens=8192)

    def clean_import_markdown(
        self,
        markdown: str,
        media_assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Clean Pandoc Markdown before question structuring."""
        media_json = json.dumps(media_assets, ensure_ascii=False, indent=2)
        system_prompt = """你是一位高中物理题库导入清洗助手。请清洗 Pandoc 转出的 Markdown，为后续“一题一个 JSON”的结构化识别做准备。

必须严格遵守：
1. 不要切题，不要生成题目 JSON，只输出清洗后的 Markdown。
2. 保留所有题干、选项、答案、解析、表格、图片引用，不要擅自删题。
3. 删除页眉、页脚、页码、学校水印、重复目录、无意义分隔线。
4. 统一公式格式：行内公式使用 $...$，块公式使用 $$...$$。
5. 保留 Markdown 图片语法，不要改图片路径；如果图片和上下文明显错位，可只调整图片所在段落位置。
6. 输出合法 JSON，不要添加 markdown 代码块。

返回格式：
{
  "cleaned_markdown": "清洗后的完整 Markdown",
  "warnings": ["无法确定的问题或图片关联风险"]
}"""
        user_prompt = (
            "【图片清单】\n"
            f"{media_json}\n\n"
            "【待清洗 Markdown】\n"
            f"{markdown}"
        )
        result = self._call(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=12000,
            response_format={"type": "json_object"},
        )
        # Guard: if the model's answer was captured only as raw `text` that
        # itself contains the JSON object, re-parse it so callers never see
        # a JSON-string masquerading as markdown.
        if "cleaned_markdown" not in result:
            raw_text = str(result.get("text", "")).strip()
            if raw_text.startswith("{") and "cleaned_markdown" in raw_text:
                try:
                    nested = json.loads(raw_text)
                    if isinstance(nested, dict):
                        result = nested
                except json.JSONDecodeError:
                    pass
        return result

    def refine_import_questions(
        self,
        questions: list[dict[str, Any]],
        batch_size: int = 5,
        time_budget_seconds: float = 240.0,
    ) -> dict[str, Any]:
        """AI-refine locally-split exam questions into standard JSON.

        The local splitter has already bound images as ``![fig:xxx]``
        placeholders; the model must keep those markers and the ``figures``
        arrays untouched. Returns {"questions": [...], "refined_count": N}.
        Falls back per-batch to the local items when a call fails, and stops
        calling the AI entirely once ``time_budget_seconds`` is exceeded so a
        slow/unreachable model can never freeze the import pipeline.
        """
        from .import_refiner import refine_import_questions_concurrent

        return refine_import_questions_concurrent(
            questions=questions,
            call=self._call,
            batch_size=batch_size,
            max_workers=3,
            time_budget_seconds=time_budget_seconds,
        )

    def refine_question_format(self, question: dict[str, Any]) -> dict[str, Any]:
        """Fix presentation and LaTeX syntax without rewriting a question."""
        source = {
            "question_id": str(question.get("question_id") or ""),
            "question_type": str(question.get("question_type") or ""),
            "title": str(question.get("title") or ""),
            "options": question.get("options") if isinstance(question.get("options"), list) else [],
            "answer": str(question.get("answer") or ""),
            "analysis": str(question.get("analysis") or ""),
        }
        system_prompt = """你是高中物理题库的格式校对助手。只修复格式，不得改变题意、条件、数值、单位、选项含义、答案或解题结论。

请处理中文与 LaTeX 混排中的常见问题：
1. 行内公式统一为 $...$，独占一行的公式才使用 $$...$$；不要输出 \\( ... \\) 或 \\[ ... \\]。
2. 修正显然的 LaTeX 转义、花括号和分隔符问题，例如 \\varphi、\\frac、\\leq；保留题图占位符 ![fig:...] 原样不动。
   欧姆单位是高频错误：必须写成数学模式中的 `\\Omega`，推荐将数值和单位合为 `$300.0\\,\\Omega$`。严禁输出 `\\text{\\Omega}`、`$\\text{\\Omega}$`、裸露的 `\\Omega` 或把 `\\Omega` 当普通文字。示例：`300.0$\\text{\\Omega}$` 必须优化为 `$300.0\\,\\Omega$`；`17.0k\\text{\\Omega}` 必须优化为 `$17.0\\,\\mathrm{k}\\Omega$`。
3. 识别数据表格。由横线、空格或制表符分列的数据，必须转成标准 Markdown 表格：首行为表头，第二行为 | --- | 分隔行，后续为数据行；每行列数必须相同。表格中的数值、单位和公式不得改变。
4. OCR 的单行断行通常不表示换段。你必须自行判断并合并同一段的软换行，不能因为原文换行就保留它。删除没有语义作用的空白行：题干、分问、步骤和选项之间不得用空白行人为拉开；相邻内容最多保留一个换行，禁止输出连续空行。仅真正独立的行间公式、图片占位符或表格可保留必要的换行，但其前后也不得出现多余空白行。特别是下面的输入必须原样按语义合成一行：
输入：持续时间为\n$\\Delta t$\n，经过狭缝后……\n输出：持续时间为$\\Delta t$，经过狭缝后……
只在自然段、列表、表格、图片占位符或真正独立的行间公式处保留换行。选项只能保留原有选项字母和数量。
5. 删除 OCR 误插入的编号噪声：解析中出现的 `\\[1]`、`[1]`、`\\[10]` 等方括号编号不是题目内容时必须删除；由这些编号拆出的孤立连续数字行（例如单独占行的 `4`、`5`、`6`、`7`）也必须删除。保留题目开头的正式题号、选项字母、数值/单位、公式下标，以及真实分问标记 `（1）`、`（2）`。
6. 当 `question_type` 为 `experiment` 时，A/B/C 等不是选择项，而是实验步骤。必须将它们按顺序并入 `title` 的“实验步骤”正文，改为 `（1）（2）（3）` 步骤编号，并返回空数组 `options: []`。实验题绝不能保留选择题选项。
7. 信息不确定时保持原文，绝不补写、删减或推断物理内容。

只返回 JSON，不要 Markdown：
{"question_id":"原样保留","title":"...","options":[{"opt":"A","content":"..."}],"answer":"...","analysis":"..."}"""
        source_json = json.dumps(source, ensure_ascii=False)
        # Formatting does not need V4-Pro's slower reasoning path. Use Flash
        # only for the official DeepSeek V4 endpoint; custom OpenAI-compatible
        # providers retain the model explicitly configured by the user.
        format_model = self._model
        if self._base_url.rstrip("/") == "https://api.deepseek.com" and self._model == "deepseek-v4-pro":
            format_model = "deepseek-v4-flash"
        # Keep enough room to return the complete question but avoid asking a
        # short formatting request to reserve a 6K-token response.
        format_max_tokens = min(6000, max(1200, int(len(source_json) * 1.25) + 300))

        result = self._call(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": source_json},
            ],
            temperature=0,
            max_tokens=format_max_tokens,
            response_format={"type": "json_object"},
            timeout_seconds=min(60, self._timeout),
            model_name=format_model,
            thinking="disabled",
        )

        merged = dict(source)
        for field in ("title", "answer", "analysis"):
            value = result.get(field)
            if isinstance(value, str):
                merged[field] = value.strip()

        candidate_options = result.get("options")
        if source["question_type"] == "experiment" and isinstance(candidate_options, list) and len(candidate_options) == 0:
            merged["options"] = []
        elif isinstance(candidate_options, list) and len(candidate_options) == len(source["options"]):
            original_by_opt = {
                str(item.get("opt") or "").strip().upper(): item
                for item in source["options"]
                if isinstance(item, dict)
            }
            refined_by_opt = {
                str(item.get("opt") or "").strip().upper(): item
                for item in candidate_options
                if isinstance(item, dict)
            }
            if original_by_opt and set(original_by_opt) == set(refined_by_opt):
                merged["options"] = [
                    {
                        **original,
                        "content": str(refined_by_opt[opt].get("content") or "").strip(),
                    }
                    for opt, original in original_by_opt.items()
                ]
        return merged

    def parse_document(
        self,
        file_path: str,
        file_type: str,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """
        Parse a document (PDF/image) via vision model.

        For image types, we can send the image as a base64 data URL.
        For PDF, we rely on the server having access to the file path.
        """
        import base64
        import pathlib

        system_prompt = """你是一位专业的高中物理试卷 OCR 与题库结构化助手。请识别图片/PDF页面中的所有题目，并输出标准 JSON。

严格要求：
1. 一题一个 JSON 对象，不要把多道题合并。
2. 公式统一转成 LaTeX：行内 $...$，块公式 $$...$$。
3. 选择题选项放入 options，选项内容不要保留 "A." 前缀。
4. 若答案/解析不可见，answer 和 analysis 置为空字符串。
5. 尽量过滤页眉、页脚、页码、水印、无关说明。
6. 只输出 JSON，不要 markdown 代码块，不要解释。

返回格式：
{
  "document_type": "pdf|image",
  "page_count": 1,
  "questions": [
    {
      "question_id": "",
      "question_type": "single_choice|multi_choice|fill|experiment|calculation",
      "title": "题干文本",
      "options": [{"opt": "A", "content": "选项内容"}],
      "answer": "",
      "analysis": "",
      "figures": [],
      "difficulty": null,
      "knowledge_point": "",
      "tags": [],
      "source_page": 1,
      "raw_text": ""
    }
  ]
}"""

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        def image_message_items(paths: list[pathlib.Path]) -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = [
                {"type": "text", "text": "请识别以下试卷页面，按题目切分并生成标准 JSON。"}
            ]
            for idx, path in enumerate(paths, start=1):
                img_bytes = path.read_bytes()
                img_b64 = base64.b64encode(img_bytes).decode("ascii")
                ext = path.suffix.lower().lstrip(".") or "png"
                if ext == "jpg":
                    ext = "jpeg"
                items.append({"type": "text", "text": f"第 {idx} 页/图："})
                items.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{ext};base64,{img_b64}"},
                    "min_pixels": 32 * 32 * 3,
                    "max_pixels": 32 * 32 * 8192,
                })
            return items

        # If it's an image type, read and attach as vision input.
        image_types = {"jpg", "jpeg", "png", "webp"}
        if file_type.lower() in image_types:
            path = pathlib.Path(file_path)
            if not path.is_file():
                raise RuntimeError(f"图片文件不存在：{file_path}")
            try:
                content = image_message_items([path])
            except OSError as exc:
                raise RuntimeError(f"读取图片失败，无法进入 OCR：{exc}") from exc
            messages.append({
                "role": "user",
                "content": content,
            })
            return self._call(messages, temperature=0.1, max_tokens=8192)

        if file_type.lower() == "pdf":
            path = pathlib.Path(file_path)
            if not path.is_file():
                raise RuntimeError(f"PDF 文件不存在：{file_path}")
            try:
                import tempfile
                import pypdfium2 as pdfium

                with tempfile.TemporaryDirectory(prefix="physics_vault_pdf_ocr_") as tmpdir:
                    pdf = pdfium.PdfDocument(str(path))
                    page_count = len(pdf)
                    page_images: list[pathlib.Path] = []
                    for page_index in range(min(page_count, 8)):
                        page = pdf[page_index]
                        bitmap = page.render(scale=2.0)
                        pil_image = bitmap.to_pil()
                        target = pathlib.Path(tmpdir) / f"page_{page_index + 1:03d}.png"
                        pil_image.save(target)
                        page_images.append(target)
                    messages.append({
                        "role": "user",
                        "content": image_message_items(page_images),
                    })
                    result = self._call(messages, temperature=0.1, max_tokens=16000)
                    result.setdefault("document_type", "pdf")
                    result.setdefault("page_count", page_count)
                    return result
            except ModuleNotFoundError as exc:
                raise RuntimeError("PDF OCR 需要安装 pypdfium2：请在后端环境执行 pip install -r apps/api/requirements.txt") from exc
            except Exception as exc:
                logger.warning("Failed to render PDF for vision API: %s", exc)
                raise RuntimeError(f"PDF 渲染为图片失败，无法进入 OCR：{exc}") from exc

        raise RuntimeError(f"不支持的视觉识别文件类型：{file_type}")

    def generate_question_variants(
        self,
        source_question: dict[str, Any],
        variant_mode: str,
        count: int = 3,
        keep_knowledge_points: bool = True,
        target_difficulty: int | None = None,
    ) -> dict[str, Any]:
        """Generate variant questions from a source question."""
        mode_desc = {
            "change_condition": "改变题目的条件参数",
            "change_question": "改变提问方式",
            "change_numbers": "改变题目中的数字",
            "same_model_new_context": "保持物理模型不变，更换场景",
            "difficulty_up": "生成更难的变体",
            "difficulty_down": "生成更简单的变体",
        }.get(variant_mode, "生成变体题目")

        q_json = json.dumps(source_question, ensure_ascii=False, indent=2)
        system_prompt = (
            f"你是一位高中物理出题专家。请根据原题，{mode_desc}，生成{count}道变体题目。"
            f"{'请保持知识点不变。' if keep_knowledge_points else ''}"
            f"{'目标难度：' + str(target_difficulty) if target_difficulty else ''}"
            "请以 JSON 格式输出：{\"variants\": [{"
            "\"title\": \"...\", \"question_type\": \"...\", "
            "\"options\": [...], \"answer\": \"...\", \"analysis\": \"...\", "
            "\"difficulty\": N, \"knowledge_point\": \"...\", \"tags\": [...]"
            "}]}"
        )
        return self._call([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": q_json},
        ], temperature=0.7, max_tokens=8192)


class DashScopeNativeOcrClient:
    """Calls DashScope native MultiModalConversation for Qwen OCR models."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str = "qwen-vl-ocr",
        timeout_seconds: int = 120,
        max_retries: int = 2,
    ) -> None:
        self._base_url = _normalize_dashscope_native_base_url(base_url)
        self._api_key = api_key
        self._model = model_name or "qwen-vl-ocr"
        self._timeout = timeout_seconds
        self._max_retries = max(1, max_retries)

    def test_connection(self) -> None:
        self._call_native([
            {
                "image": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/ctdzex/biaozhun.jpg",
            },
            {"text": "请仅输出图像中的文本内容。"},
        ])

    def parse_document(
        self,
        file_path: str,
        file_type: str,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        import pathlib

        path = pathlib.Path(file_path)
        if not path.is_file():
            raise RuntimeError(f"图片文件不存在：{file_path}")
        if file_type.lower() not in {"jpg", "jpeg", "png", "webp"}:
            raise RuntimeError(f"DashScope OCR 仅接收已渲染图片，当前文件类型：{file_type}")

        prompt = """请识别这张高中物理试卷页面中的所有题目，并返回严格 JSON。

返回格式：
{
  "document_type": "image",
  "page_count": 1,
  "questions": [
    {
      "question_id": "",
      "question_type": "single_choice|multi_choice|fill|experiment|calculation",
      "title": "题干文本，公式用 LaTeX",
      "options": [{"opt": "A", "content": "选项内容"}],
      "answer": "",
      "analysis": "",
      "figures": [],
      "difficulty": null,
      "knowledge_point": "",
      "tags": [],
      "source_page": 1,
      "raw_text": "本页原始 OCR 文本"
    }
  ]
}

要求：
1. 一题一个对象，不要合并多题。
2. 只输出 JSON，不要 markdown 代码块，不要解释。
3. 若答案或解析不可见，置为空字符串。
4. 公式尽量转成 LaTeX；看不清的单个字符用 ? 代替。"""

        content = [
            {"image": str(path.resolve())},
            {"text": prompt},
        ]
        raw_text = self._call_native(content)
        parsed = AiHttpClient._parse_content(raw_text)
        if "questions" in parsed:
            parsed.setdefault("document_type", "image")
            parsed.setdefault("page_count", 1)
            return parsed
        return {
            "document_type": "image",
            "page_count": 1,
            "question_count": 0,
            "questions": [],
            "raw_text": str(parsed.get("text") or raw_text or ""),
            "warnings": ["DashScope OCR 返回了文本，但未返回题目 JSON"],
        }

    def _call_native(self, content: list[dict[str, Any]]) -> str:
        import dashscope
        from dashscope import MultiModalConversation

        dashscope.base_http_api_url = self._base_url
        messages = [{"role": "user", "content": content}]
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = MultiModalConversation.call(
                    api_key=self._api_key,
                    model=self._model,
                    messages=messages,
                )
                status_code = getattr(response, "status_code", 200)
                if status_code and int(status_code) >= 400:
                    message = getattr(response, "message", "") or getattr(response, "code", "") or str(response)
                    raise RuntimeError(f"DashScope OCR 调用失败：HTTP {status_code}，{message}")
                return _extract_dashscope_text(response)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "DashScope OCR call attempt %d/%d failed: %s",
                    attempt + 1,
                    self._max_retries,
                    exc,
                )
        raise RuntimeError(
            f"DashScope OCR 调用失败（已重试 {self._max_retries} 次）\n"
            f"目标 URL: {self._base_url}\n模型: {self._model}\n最后错误: {last_error}"
        )


def _extract_dashscope_text(response: Any) -> str:
    output = getattr(response, "output", None)
    choices = getattr(output, "choices", None)
    if not choices and isinstance(output, dict):
        choices = output.get("choices")
    if not choices:
        return str(response)

    message = choices[0].get("message") if isinstance(choices[0], dict) else getattr(choices[0], "message", None)
    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item["text"]))
                elif "content" in item:
                    parts.append(str(item["content"]))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(part for part in parts if part.strip())
    if isinstance(content, str):
        return content
    return str(content or "")


def _normalize_dashscope_native_base_url(base_url: str) -> str:
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return "https://dashscope.aliyuncs.com/api/v1"
    if "dashscope.aliyuncs.com/compatible-mode" in raw:
        return "https://dashscope.aliyuncs.com/api/v1"
    if raw.endswith("/api/v1"):
        return raw
    return raw
