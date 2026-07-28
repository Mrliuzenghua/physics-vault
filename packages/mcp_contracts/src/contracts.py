from __future__ import annotations

from typing import Protocol

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
    ParseDocumentInput,
    ParseDocumentOutput,
    ParseQuestionRegionInput,
    ParseQuestionRegionOutput,
)


class DocumentParser(Protocol):
    async def parse_document(self, input: ParseDocumentInput) -> ParseDocumentOutput: ...

    async def detect_question_regions(self, input: DetectQuestionRegionsInput) -> DetectQuestionRegionsOutput: ...

    async def parse_question_region(self, input: ParseQuestionRegionInput) -> ParseQuestionRegionOutput: ...


class AnalysisGenerator(Protocol):
    async def generate_analysis(self, input: GenerateAnalysisInput) -> GenerateAnalysisOutput: ...


class KnowledgeGenerator(Protocol):
    async def generate_knowledge(self, input: GenerateKnowledgeInput) -> GenerateKnowledgeOutput: ...


class MetadataGenerator(Protocol):
    async def generate_metadata(self, input: GenerateMetadataInput) -> GenerateMetadataOutput: ...


class QuestionVariantGenerator(Protocol):
    async def generate_question_variants(self, input: GenerateQuestionVariantsInput) -> GenerateQuestionVariantsOutput: ...
