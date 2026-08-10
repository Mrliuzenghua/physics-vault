from physics_vault_api.services.document_converter import PandocAdapter as ConverterPandocAdapter
from physics_vault_api.services.document_pipeline import PandocAdapter as PipelinePandocAdapter


def test_document_pipeline_keeps_pandoc_adapter_import_compatible() -> None:
    assert PipelinePandocAdapter is ConverterPandocAdapter
