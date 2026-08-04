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
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            body["response_format"] = response_format

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
        """Generate teaching analysis for a physics question.

        Returns a structured JSON matching the database schema so the
        frontend can render every field directly.
        """
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

        system_prompt = """你是一位资深高中物理教师和题库编辑。请根据题目内容，生成完整的结构化题目数据。

严格按以下 JSON 格式输出（不要添加 markdown 代码块标记）：

{
  "question_type": "calculation",
  "difficulty": 3,
  "knowledge_point": "匀变速直线运动",
  "tags": ["力学", "运动学"],
  "source": "自编",
  "options": [
    {"opt": "A", "content": "25m"},
    {"opt": "B", "content": "50m"}
  ],
  "answer": "B",
  "analysis": "完整的题目解析，包含考点分析、解题步骤、易错提醒。用自然中文段落表述。",
  "sub_questions": []
}

字段说明：
- question_type: single_choice(单选) / multi_choice(多选) / fill(填空) / experiment(实验) / calculation(计算)
- difficulty: 1-5 整数，1最简单5最难
- knowledge_point: 最匹配的知识点名称，取最细粒度
- tags: 2-5个标签，如"力学""电磁学""热学""光学""原子物理"
- source: 题目来源推测，如"高考真题""模拟题""自编"
- options: 选项列表，每个有 opt(ABCD) 和 content(内容)
- answer: 正确答案
- analysis: 详细解析，200-500字
- sub_questions: 子问题列表（通常为空数组）

如果题目信息不完整，请根据题干尽力推理补全。保证返回合法的 JSON。"""

        if style == "classroom_brief":
            extra = "\n请生成课堂教学用的简要解析（150-300字）。"
        elif style == "self_study_full":
            extra = "\n请生成自习用的详尽解析（500字以上）。"
        elif style == "exam_standard":
            extra = "\n请生成考试标准答案格式的解析。"
        else:
            extra = ""

        return self._call([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question_text + extra},
        ], temperature=0.3, max_tokens=4096)

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
