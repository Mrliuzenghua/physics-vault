from physics_vault_api.schemas.import_pipeline import CleanDocumentRequest
from physics_vault_api.services.document_pipeline import DocumentCleaningService
from physics_vault_api.services.import_text_cleaner import ImportTextCleaner


def test_clean_text_normalizes_configured_import_artifacts() -> None:
    result = ImportTextCleaner.clean_text(
        "第 1 页\r\n\r\n  速度\\(v\\)   \r\n\r\n\r\n共 2 页",
        normalize_whitespace=True,
        strip_headers_footers=True,
        normalize_math_delimiters=True,
        remove_blank_lines=True,
    )

    assert result == {
        "cleaned_text": "速度$v$",
        "original_length": 32,
        "cleaned_length": 5,
    }


def test_clean_markdown_preserves_unmatched_images_as_warnings() -> None:
    result = ImportTextCleaner.clean_markdown_for_import(
        "1 / 共 2 页\n---\n![](missing.png)\n\n\n正文 \\[E=mc^2\\]",
        media_assets=[{"filename": "bound.png"}],
    )

    assert result["cleaned_text"] == "![](missing.png)\n\n正文 $E=mc^2$"
    assert result["warnings"] == ["Unmatched image reference kept: ![](missing.png)"]


def test_document_cleaning_service_remains_a_compatible_cleaner_facade() -> None:
    payload = CleanDocumentRequest(source_text="第 1 页\n  速度\\(v\\)  \n\n共 2 页")

    assert DocumentCleaningService().clean(payload) == ImportTextCleaner.clean_text(
        payload.source_text,
        normalize_whitespace=payload.normalize_whitespace,
        strip_headers_footers=payload.strip_headers_footers,
        normalize_math_delimiters=payload.normalize_math_delimiters,
        remove_blank_lines=payload.remove_blank_lines,
    )
