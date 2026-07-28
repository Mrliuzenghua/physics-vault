from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from .client import McpCallOptions, McpClient
from .contracts import AnalysisGenerator, DocumentParser, KnowledgeGenerator, MetadataGenerator, QuestionVariantGenerator
from .errors import AppError, AppWarning, ensure
from .models import (
    DetectQuestionRegionsInput,
    DetectQuestionRegionsOutput,
    GenerateAnalysisInput,
    GenerateAnalysisOutput,
    GenerateKnowledgeInput,
    GenerateKnowledgeOutput,
    GenerateMetadataInput,
    GenerateMetadataOutput,
    GenerateQuestionVariantsInput,
    GenerateQuestionVariantsOutput,
    MetadataTaskResultItem,
    ParseDocumentInput,
    ParseDocumentOutput,
    ParseQuestionRegionInput,
    ParseQuestionRegionOutput,
    ParsedPage,
    ParsedQuestionDraft,
    ParsedRegion,
    QuestionOption,
    StandardQuestion,
    VariantQuestion,
)

MockMode = Literal["success", "partial_failure", "invalid_json", "timeout", "empty_result"]


def _request(tool_payload: dict[str, Any], task_id: str) -> dict[str, Any]:
    return {
        "version": "1.0",
        "request_id": str(uuid.uuid4()),
        "task_id": task_id,
        "payload": tool_payload,
    }


class McpDocumentParser(DocumentParser):
    def __init__(self, client: McpClient, timeout_ms: int = 60000) -> None:
        self._client = client
        self._timeout_ms = timeout_ms

    async def parse_document(self, input: ParseDocumentInput) -> ParseDocumentOutput:
        req = _request(
            {
                "document": {"file_path": input.file_path, "file_type": input.file_type},
                "mode": input.mode,
                "options": {
                    "enable_preprocess": input.enable_preprocess,
                    "enable_region_detection": input.enable_region_detection,
                    "enable_figure_extraction": input.enable_figure_extraction,
                    "enable_table_extraction": input.enable_table_extraction,
                    "formula_format": input.formula_format,
                    "ignore_headers_footers": input.ignore_headers_footers,
                },
            },
            input.batch_id,
        )
        resp = await self._client.call("parse_document", req, McpCallOptions(timeout_ms=self._timeout_ms))
        if not resp.success or resp.result is None:
            raise AppError(code="MCP_CALL_FAILED", message="parse_document failed", retryable=True)
        return ParseDocumentOutput(
            document_type=str(resp.result.get("document_type", "unknown")),
            pages=[
                ParsedPage(
                    page_no=int(page.get("page_no", 0)),
                    image_path=str(page.get("image_path", "")),
                    question_regions=[
                        ParsedRegion(
                            region_id=str(region.get("region_id", "")),
                            bbox=tuple(region.get("bbox", [0, 0, 0, 0])),
                            preview_path=str(region.get("preview_path", "")),
                            status=str(region.get("status", "parsed")),
                        )
                        for region in page.get("question_regions", [])
                    ],
                )
                for page in resp.result.get("pages", [])
            ],
            questions=[_draft_from_dict(item) for item in resp.result.get("questions", [])],
            warnings=[AppWarning(**warning.model_dump()) for warning in resp.warnings],
        )

    async def detect_question_regions(self, input: DetectQuestionRegionsInput) -> DetectQuestionRegionsOutput:
        req = _request(
            {
                "page_image": input.page_image,
                "options": {
                    "detect_sub_questions": input.detect_sub_questions,
                    "merge_nearby_blocks": input.merge_nearby_blocks,
                    "ignore_small_noise": input.ignore_small_noise,
                },
            },
            input.batch_id,
        )
        resp = await self._client.call("detect_question_regions", req, McpCallOptions(timeout_ms=self._timeout_ms))
        if not resp.success or resp.result is None:
            raise AppError(code="MCP_CALL_FAILED", message="detect_question_regions failed", retryable=True)
        return DetectQuestionRegionsOutput(
            page_no=resp.result.get("page_no"),
            regions=list(resp.result.get("regions", [])),
        )

    async def parse_question_region(self, input: ParseQuestionRegionInput) -> ParseQuestionRegionOutput:
        req = _request(
            {
                "region": {"region_id": input.region_id, "image_path": input.image_path},
                "options": {
                    "extract_figures": input.extract_figures,
                    "extract_tables": input.extract_tables,
                    "formula_format": input.formula_format,
                },
            },
            input.batch_id,
        )
        resp = await self._client.call("parse_question_region", req, McpCallOptions(timeout_ms=self._timeout_ms))
        if not resp.success or resp.result is None:
            raise AppError(code="MCP_CALL_FAILED", message="parse_question_region failed", retryable=True)
        return ParseQuestionRegionOutput(question=_draft_from_dict(resp.result["question"]))


class McpAnalysisGenerator(AnalysisGenerator):
    def __init__(self, client: McpClient, timeout_ms: int = 20000) -> None:
        self._client = client
        self._timeout_ms = timeout_ms

    async def generate_analysis(self, input: GenerateAnalysisInput) -> GenerateAnalysisOutput:
        req = _request(
            {
                "question": _question_to_dict(input.question),
                "style": input.style,
                "options": {
                    "include_extension": input.include_extension,
                    "allow_figure_refs": input.allow_figure_refs,
                },
            },
            input.question.question_id,
        )
        resp = await self._client.call("generate_analysis", req, McpCallOptions(timeout_ms=self._timeout_ms))
        if not resp.success or resp.result is None:
            raise AppError(code="MCP_CALL_FAILED", message="generate_analysis failed", retryable=True)
        ensure(
            resp.result.get("question_id") == input.question.question_id,
            code="QUESTION_ID_MISMATCH",
            message="Returned question_id does not match input",
        )
        return GenerateAnalysisOutput(
            question_id=input.question.question_id,
            structured=dict(resp.result.get("analysis_structured", {})),
            text=str(resp.result.get("analysis_text", "")),
            warnings=[AppWarning(**warning.model_dump()) for warning in resp.warnings],
        )


class McpKnowledgeGenerator(KnowledgeGenerator):
    def __init__(self, client: McpClient, timeout_ms: int = 25000) -> None:
        self._client = client
        self._timeout_ms = timeout_ms

    async def generate_knowledge(self, input: GenerateKnowledgeInput) -> GenerateKnowledgeOutput:
        req = _request(
            {
                "knowledge_points": input.knowledge_points,
                "style": input.style,
                "length": input.length,
                "options": {
                    "include_formula": input.include_formula,
                    "include_common_mistakes": input.include_common_mistakes,
                },
            },
            hashlib.sha256("|".join(input.knowledge_points).encode("utf-8")).hexdigest()[:16],
        )
        resp = await self._client.call("generate_knowledge", req, McpCallOptions(timeout_ms=self._timeout_ms))
        if not resp.success or resp.result is None:
            raise AppError(code="MCP_CALL_FAILED", message="generate_knowledge failed", retryable=True)
        return GenerateKnowledgeOutput(
            knowledge_key=str(resp.result.get("knowledge_key", "")),
            title=str(resp.result.get("title", "")),
            content=str(resp.result.get("content", "")),
            outline=list(resp.result.get("outline", [])),
            warnings=[AppWarning(**warning.model_dump()) for warning in resp.warnings],
        )


class McpMetadataGenerator(MetadataGenerator):
    def __init__(self, client: McpClient, timeout_ms: int = 40000) -> None:
        self._client = client
        self._timeout_ms = timeout_ms

    async def generate_metadata(self, input: GenerateMetadataInput) -> GenerateMetadataOutput:
        req = _request(
            {
                "questions": [item.__dict__ for item in input.items],
                "fields": input.fields,
                "constraints": input.constraints.__dict__,
                "options": {
                    "only_fill_empty": input.only_fill_empty,
                    "strict_enum_match": input.strict_enum_match,
                },
                "prompt_append": input.prompt_append,
            },
            str(uuid.uuid4()),
        )
        resp = await self._client.call("generate_metadata", req, McpCallOptions(timeout_ms=self._timeout_ms))
        if not resp.success or resp.result is None:
            raise AppError(code="MCP_CALL_FAILED", message="generate_metadata failed", retryable=True)
        items = [MetadataTaskResultItem(**item) for item in resp.result.get("items", [])]
        ensure(
            len(items) == len(input.items),
            code="QUESTION_ID_MISMATCH",
            message="Metadata item count does not match input item count",
        )
        source_ids = {item.id for item in input.items}
        ensure(
            {item.id for item in items} == source_ids,
            code="QUESTION_ID_MISMATCH",
            message="Metadata result ids do not match input ids",
        )
        return GenerateMetadataOutput(
            items=items,
            warnings=[AppWarning(**warning.model_dump()) for warning in resp.warnings],
        )


@dataclass(slots=True)
class MockConfig:
    mode: MockMode = "success"
    delay_ms: int = 0


class MockDocumentParser(DocumentParser):
    def __init__(self, config: MockConfig | None = None) -> None:
        self._config = config or MockConfig()

    async def parse_document(self, input: ParseDocumentInput) -> ParseDocumentOutput:
        return ParseDocumentOutput(
            document_type="mock_pdf",
            pages=[ParsedPage(page_no=1, image_path=input.file_path, question_regions=[ParsedRegion("region_001", (100, 100, 800, 600), "./mock/region_001.png")])],
            questions=[
                ParsedQuestionDraft(
                    question_id="tmp_q_001",
                    question_type="single_choice",
                    title="已知物体做匀加速直线运动，求其加速度。",
                    options=[QuestionOption(opt="A", content="1 m/s^2"), QuestionOption(opt="B", content="2 m/s^2")],
                    source_page=1,
                    source_region_id="region_001",
                    raw_text="mock raw text",
                    confidence=0.95,
                )
            ],
        )

    async def detect_question_regions(self, input: DetectQuestionRegionsInput) -> DetectQuestionRegionsOutput:
        return DetectQuestionRegionsOutput(page_no=1, regions=[{"region_id": "region_001", "bbox": [100, 100, 800, 600], "region_type": "question"}])

    async def parse_question_region(self, input: ParseQuestionRegionInput) -> ParseQuestionRegionOutput:
        return ParseQuestionRegionOutput(
            question=ParsedQuestionDraft(
                question_id="tmp_q_single",
                question_type="calculation",
                title="求物块在斜面上的加速度。",
                source_page=1,
                source_region_id=input.region_id,
                raw_text="mock region text",
                confidence=0.96,
            )
        )


class MockAnalysisGenerator(AnalysisGenerator):
    async def generate_analysis(self, input: GenerateAnalysisInput) -> GenerateAnalysisOutput:
        return GenerateAnalysisOutput(
            question_id=input.question.question_id,
            structured={
                "review": "审题分析",
                "strategy": "解题思路",
                "steps": "规范步骤",
                "conclusion": "最终结论",
                "pitfalls": "易错警示",
                "extension": "拓展设问",
            },
            text="这是一个 mock 解析结果。",
        )


class MockKnowledgeGenerator(KnowledgeGenerator):
    async def generate_knowledge(self, input: GenerateKnowledgeInput) -> GenerateKnowledgeOutput:
        return GenerateKnowledgeOutput(
            knowledge_key=hashlib.sha256("|".join(input.knowledge_points).encode("utf-8")).hexdigest()[:16],
            title="专题知识点总结",
            content="这是一个 mock 知识点区块。",
            outline=["核心概念", "常见模型", "易错点"],
        )


class MockMetadataGenerator(MetadataGenerator):
    async def generate_metadata(self, input: GenerateMetadataInput) -> GenerateMetadataOutput:
        items = []
        for item in input.items:
            items.append(
                MetadataTaskResultItem(
                    id=item.id,
                    knowledgePoints=["力学/牛顿运动定律/受力分析"] if "knowledgePoints" in input.fields else None,
                    tags=["整体法", "牛顿第二定律"] if "tags" in input.fields else None,
                    category="计算题" if "category" in input.fields else None,
                    difficulty=3 if "difficulty" in input.fields else None,
                )
            )
        return GenerateMetadataOutput(items=items)


class DisabledDocumentParser(DocumentParser):
    async def parse_document(self, input: ParseDocumentInput) -> ParseDocumentOutput:
        raise AppError(code="AI_DISABLED", message="AI service is disabled", retryable=False)

    async def detect_question_regions(self, input: DetectQuestionRegionsInput) -> DetectQuestionRegionsOutput:
        raise AppError(code="AI_DISABLED", message="AI service is disabled", retryable=False)

    async def parse_question_region(self, input: ParseQuestionRegionInput) -> ParseQuestionRegionOutput:
        raise AppError(code="AI_DISABLED", message="AI service is disabled", retryable=False)


class DisabledAnalysisGenerator(AnalysisGenerator):
    async def generate_analysis(self, input: GenerateAnalysisInput) -> GenerateAnalysisOutput:
        raise AppError(code="AI_DISABLED", message="AI service is disabled", retryable=False)


class DisabledKnowledgeGenerator(KnowledgeGenerator):
    async def generate_knowledge(self, input: GenerateKnowledgeInput) -> GenerateKnowledgeOutput:
        raise AppError(code="AI_DISABLED", message="AI service is disabled", retryable=False)


class DisabledMetadataGenerator(MetadataGenerator):
    async def generate_metadata(self, input: GenerateMetadataInput) -> GenerateMetadataOutput:
        raise AppError(code="AI_DISABLED", message="AI service is disabled", retryable=False)


# ── Question Variant Generation ──


class McpQuestionVariantGenerator(QuestionVariantGenerator):
    def __init__(self, client: McpClient, timeout_ms: int = 40000) -> None:
        self._client = client
        self._timeout_ms = timeout_ms

    async def generate_question_variants(
        self, input: GenerateQuestionVariantsInput
    ) -> GenerateQuestionVariantsOutput:
        req = _request(
            {
                "source_question": {
                    "question_id": input.source_question.question_id,
                    "question_type": input.source_question.question_type,
                    "title": input.source_question.title,
                    "options": input.source_question.options,
                    "answer": input.source_question.answer,
                    "analysis": input.source_question.analysis,
                    "difficulty": input.source_question.difficulty,
                    "knowledge_point": input.source_question.knowledge_point,
                    "tags": input.source_question.tags,
                    "source": input.source_question.source,
                },
                "variant_mode": input.variant_mode,
                "count": input.count,
                "instructions": input.instructions,
                "target_difficulty": input.target_difficulty,
                "keep_knowledge_points": input.keep_knowledge_points,
            },
            input.source_question.question_id,
        )
        resp = await self._client.call(
            "generate_question_variants", req, McpCallOptions(timeout_ms=self._timeout_ms)
        )
        if not resp.success or resp.result is None:
            raise AppError(
                code="MCP_CALL_FAILED", message="generate_question_variants failed", retryable=True
            )
        variants = [
            VariantQuestion(
                question_type=str(v.get("question_type", "calculation")),
                title=str(v.get("title", "")),
                options=[dict(o) for o in v.get("options", [])],
                answer=str(v.get("answer", "")),
                analysis=str(v.get("analysis", "")),
                difficulty=v.get("difficulty"),
                knowledge_point=v.get("knowledge_point"),
                tags=list(v.get("tags", [])),
                source=v.get("source"),
                derived_from_question_id=input.source_question.question_id,
                variant_mode=input.variant_mode,
                variant_note=v.get("variant_note"),
            )
            for v in resp.result.get("variants", [])
        ]
        return GenerateQuestionVariantsOutput(
            variants=variants,
            warnings=[AppWarning(**w) for w in resp.warnings],
        )


class MockQuestionVariantGenerator(QuestionVariantGenerator):
    async def generate_question_variants(
        self, input: GenerateQuestionVariantsInput
    ) -> GenerateQuestionVariantsOutput:
        sq = input.source_question
        variants: list[VariantQuestion] = []
        for i in range(min(input.count, 5)):
            variants.append(
                VariantQuestion(
                    question_type=sq.question_type,
                    title=f"[变式 {i+1}] {sq.title}" if i > 0 else f"[变式] {sq.title}",
                    options=sq.options,
                    answer=f"[变式答案 {i+1}] {sq.answer}",
                    analysis=f"[变式解析 {i+1}] {sq.analysis}",
                    difficulty=input.target_difficulty or sq.difficulty,
                    knowledge_point=sq.knowledge_point if input.keep_knowledge_points else None,
                    tags=list(sq.tags),
                    source=sq.source,
                    derived_from_question_id=sq.question_id,
                    variant_mode=input.variant_mode,
                    variant_note=f"Mock variant #{i+1} for mode={input.variant_mode}",
                )
            )
        return GenerateQuestionVariantsOutput(variants=variants)


class DisabledQuestionVariantGenerator(QuestionVariantGenerator):
    async def generate_question_variants(
        self, input: GenerateQuestionVariantsInput
    ) -> GenerateQuestionVariantsOutput:
        raise AppError(code="AI_DISABLED", message="AI service is disabled", retryable=False)


def _draft_from_dict(data: dict[str, Any]) -> ParsedQuestionDraft:
    return ParsedQuestionDraft(
        question_id=str(data.get("question_id", "")),
        question_type=str(data.get("question_type", "calculation")),  # type: ignore[arg-type]
        title=str(data.get("title", "")),
        options=[QuestionOption(**item) for item in data.get("options", [])],
        answer=str(data.get("answer", "")),
        analysis=str(data.get("analysis", "")),
        sub_questions=[],
        figures=[],
        difficulty=data.get("difficulty"),
        knowledge_point=data.get("knowledge_point"),
        tags=list(data.get("tags", [])),
        source=data.get("source"),
        import_batch_id=data.get("import_batch_id"),
        source_page=int(data.get("source_page", 0)),
        source_region_id=str(data.get("source_region_id", "")),
        raw_text=str(data.get("raw_text", "")),
        confidence=float(data.get("confidence", 0.0)),
    )


def _question_to_dict(question: StandardQuestion) -> dict[str, Any]:
    return {
        "question_id": question.question_id,
        "question_type": question.question_type,
        "title": question.title,
        "options": [{"opt": opt.opt, "content": opt.content} for opt in question.options],
        "answer": question.answer,
        "analysis": question.analysis,
        "sub_questions": [],
        "figures": [{"fig_uuid": fig.fig_uuid, "local_path": fig.local_path} for fig in question.figures],
        "difficulty": question.difficulty,
        "knowledge_point": question.knowledge_point,
        "tags": question.tags,
        "source": question.source,
        "import_batch_id": question.import_batch_id,
    }
