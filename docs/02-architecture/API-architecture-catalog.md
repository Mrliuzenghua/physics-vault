# API Architecture Catalog

Scope: every public HTTP endpoint assembled by `apps/api/src/physics_vault_api/application.py` and `app.py`. This catalog is the reference for API cleanup, migration, and performance work.

## Current architecture

- **188 public routes**: 3 application infrastructure routes and 185 modular-router routes; no legacy compatibility routes remain.
- Request flow: `React or MCP -> Router -> Service -> Repository -> Canonical DB or Review DB`. Long-running import and Office export work uses durable task records; Redis only transports jobs.
- Legacy compatibility endpoints are intentionally retained where callers still use root paths. New capabilities belong in a dedicated router and must not create additional root-path contracts.
- Embedding construction uses `services/embedding_runtime.py`; application startup no longer imports `legacy_app.py`. The remaining legacy file is isolated historical code pending an explicit offline-reference audit and deletion.
- Before moving the legacy review endpoints, run `python scripts/migrate_review_queue.py` to preview the canonical-to-review queue migration. Use `--apply` only after the preview reports zero conflicts; `--delete-legacy` is an explicit, final cleanup step.
- Status-bar task polling now uses `GET /api/tasks?status=...&page_size=1` and its `total`; it no longer downloads up to 50 complete legacy processing-run records every 15 seconds.

## Platform composition and frontend contract map

This is the function map for workstream 03. It complements the endpoint inventory below: the inventory answers **which endpoint exists**, while this table answers **which layer may assemble, expose, consume, or adapt it**.

| Layer / file | Owns | Must not own | Contract checkpoint |
| --- | --- | --- | --- |
| `app.py:create_app()` | Process initialization, CORS, infrastructure routes, application-container creation and Router mounting | Domain service construction or endpoint business logic | App startup includes every router returned by `ApplicationContainer.routers()` exactly once |
| `application.py:ApplicationContainer.build()` | Shared Gateway / Repository / Service instance assembly and runtime configuration recovery | HTTP mapping, page concerns or Worker → Web dependencies | Preserve construction order and shared-instance identity when extracting a domain factory |
| `application.py:ApplicationContainer.routers()` | Ordered, domain-grouped Router manifest and service injection | Recreating services or changing endpoint semantics | Every manifest change updates this catalog and passes duplicate path/method and operation-ID checks |
| `routers/*.py` | Request validation, service invocation, expected-domain-error → HTTP mapping, explicit response schema | SQL, filesystem orchestration, MCP workflow decisions or mutable closure state | JSON endpoints use a named `response_model`; downloads/streams declare their response class explicitly |
| `schemas/*.py` | Request DTOs, response DTOs and externally visible field semantics | UI state, persistence implementation or unbounded compatibility dictionaries | New public JSON contracts cannot finish as bare `dict`, `unknown[]` or `Record<string, unknown>` |
| `apps/web/src/services/apiClient.ts` | Fetch transport, JSON/FormData request rules, `ApiError` and base URL | Domain paths, normalizers or page compatibility logic | All domain clients use `requestResponse` / `request` / `requestForm`; no direct `fetch` |
| `apps/web/src/services/*Api.ts` | Domain URL construction, request serialization, response adaptation and typed DTO consumption | Page state, direct DOM work or cross-domain business orchestration | New endpoint callers land here first; functions are independently mock-testable |
| `apps/web/src/services/questionNormalizer.ts` | Legacy question-response aliases and defaults | Generic HTTP handling or component-specific fixes | All question payload compatibility is normalized before it reaches a page |
| `apps/web/src/services/api.ts` | Temporary, named compatibility re-exports | New API implementations, DTO definitions or `export *` | Existing import paths remain valid until caller migration reaches zero |
| `apps/web/src/types/<domain>.ts` and `types/index.ts` | Domain type ownership; temporary explicit barrel re-export | A catch-all model file or UI-only transient state | Types are defined by domain first and re-exported from `index.ts` only when cross-domain callers need them |

### Contract migration protocol

1. Record caller list, old/new path or fields, compatibility window, rollback route and acceptance test before changing an external contract.
2. Add the new `/api/<domain>` route, DTO and domain-client function first; retain the old path/export as an explicit compatibility layer.
3. Migrate callers, verify OpenAPI plus frontend request-level tests, then obtain integration approval before removing the compatibility layer.
4. Update this map for Router-manifest changes and update `ai-workstreams/03-platform-contracts.md` for file ownership, migration status and handoff details.

### Client migration status

| Domain | Domain client | Stable contract types | Compatibility state |
| --- | --- | --- | --- |
| Teaching projects | `teachingProjectApi.ts` | `TeachingProject`, `TeachingProjectSummary` | Completed: `api.ts` keeps named re-exports for existing callers. |
| Lesson reflections | `lessonReflectionApi.ts` | `ClassroomReflection` | Completed: local-only synchronization fields are removed before persistence. |
| Saved handouts | `lessonDocumentApi.ts` | `SavedHandoutSummary`, `SavedHandoutDocument`, `SavedHandoutVersion` | Completed: `api.ts` keeps named re-exports; the version DTO retains an index signature only for the existing untyped Handout-page state. |
| Question bank | `questionApi.ts` | `Question`, `SearchResponse`, version / knowledge-point DTOs and normalizer-owned compatibility | Completed for search, detail, batch read/write, return-to-review, versions, knowledge points and assets; do not combine it with MCP format/analysis endpoints. |

Each completed client has request-level tests for encoded IDs, bounded list parameters, expected error mapping, or payload adaptation. The retained SavedHandout-version index signature is a documented compatibility debt: remove it only after the Handout page changes its local version state from `Record<string, unknown>[]` to `SavedHandoutVersion[]`.

### Response-model migration status

| Router domain | Response-model state | Compatibility handling |
| --- | --- | --- |
| Teaching projects | Completed: list, detail, save, archive and duplicate publish `TeachingProjectListResponse` / `TeachingProjectResponse`. | The detail model permits existing persisted extension fields so snapshots and older documents are not filtered. |
| Lesson reflections | Completed: list, detail and save publish `LessonReflectionListResponse` / `LessonReflectionResponse`. | Reflection items retain extra persisted fields while their stable fields are validated. |
| Saved handouts | Completed: list, detail, save, rename, version-list and restore publish named saved-handout models. | The package and version snapshots remain opaque nested payloads pending a separate lesson-package schema migration. |

The next client split should move the remaining question-adjacent governance capabilities (images, favorites, collections, mistakes, annotations and metadata) by their own bounded domain, rather than growing `questionApi.ts` into another catch-all. The next contract gate should enforce response models for JSON Router endpoints in domains that have no deliberate file/HTML/stream exception; do not infer this from source-text formatting.

## Architecture actions

| Priority | Action | Safe implementation |
|---|---|---|
| P0 | Lightweight status polling | Completed: query the paged task endpoint for an aggregate count. |
| P1 | Legacy migration | Move the 30 compatibility routes by domain: question read/write, review, papers/statistics, embeddings. Delete both implementation and manifest key only after callers move. |
| P1 | Path normalization | New routes use `/api/<domain>`. Root routes such as `/search/questions`, `/filters/facets`, `/review-queue`, and legacy endpoints remain compatibility contracts until client migration. |
| P1 | Contract consistency | New and migrated endpoints must use explicit response models, pagination metadata, and normalized error payloads instead of bare `dict` responses. |
| P2 | Client bundle size | Dynamically load PDF and rich-editor dependencies at the page that needs them. This is independent of the API contract. |

## Infrastructure routes

| Method | Path | Responsibility |
|---|---|---|
| GET | `/health` | Process health |
| GET | `/files/{file_path:path}` | Project-root constrained file delivery |
| GET | `/thumbs/{file_path:path}` | Image thumbnail generation and cache delivery |

## `home.py` - Lightweight API entry page

| Method | Path | Handler |
|---|---|---|
| GET | `/` | `home` |

## `embedding_builds.py` - Question embedding batch construction

| Method | Path | Handler |
|---|---|---|
| POST | `/embeddings/questions/build` | `build_question_embeddings` |

## `agents.py` - Agent configuration and assisted cleanup

| Method | Path | Handler |
|---|---|---|
| GET | `/api/agents/config` | `get_config` |
| POST | `/api/agents/config` | `update_config` |
| POST | `/api/agents/test-claude-code` | `test_claude_code` |
| POST | `/api/agents/review-latex-cleanup` | `review_latex_cleanup` |
| POST | `/api/agents/question-picker` | `question_picker` |
| POST | `/api/agents/question-picker/stream` | `question_picker_stream` |

## `ai_assistant.py` - Conversational AI

| Method | Path | Handler |
|---|---|---|
| POST | `/api/ai/assistant/chat` | `chat` |

## `ai_generation.py` - AI analysis and knowledge generation

| Method | Path | Handler |
|---|---|---|
| POST | `/api/ai/analysis/generate` | `generate_analysis` |
| POST | `/api/ai/knowledge/generate` | `generate_knowledge` |
| DELETE | `/api/ai/knowledge/cache` | `clear_knowledge_cache` |
| DELETE | `/api/ai/knowledge/cache/{cache_key}` | `delete_knowledge_cache_entry` |

## `analysis_batch.py` - Batch analysis generation

| Method | Path | Handler |
|---|---|---|
| POST | `/api/ai/analysis/batch-generate` | `batch_generate_analysis` |

## `annotations.py` - Question annotations

| Method | Path | Handler |
|---|---|---|
| GET | `/api/questions/{question_id}/annotations` | `list_annotations` |
| POST | `/api/questions/{question_id}/annotations` | `create_annotation` |
| PUT | `/api/questions/annotations/{annotation_id}` | `update_annotation` |
| DELETE | `/api/questions/annotations/{annotation_id}` | `delete_annotation` |

## `assets_manager.py` - Asset inventory and controlled cleanup

| Method | Path | Handler |
|---|---|---|
| GET | `/api/assets` | `list_assets` |
| GET | `/api/assets/cleanup-preview` | `cleanup_preview` |
| GET | `/api/assets/storage-analysis` | `storage_analysis` |
| GET | `/api/assets/cache-cleanup-preview` | `cache_cleanup_preview` |
| POST | `/api/assets/cleanup-import-cache` | `cleanup_import_cache` |
| GET | `/api/assets/unused-cache-preview` | `unused_cache_preview` |
| POST | `/api/assets/cleanup-unused-cache` | `cleanup_unused_cache` |
| POST | `/api/assets/cleanup-unreferenced` | `cleanup_unreferenced` |
| DELETE | `/api/assets/{filename:path}` | `delete_asset` |

## `change_audit.py` - Change-batch audit and rollback

| Method | Path | Handler |
|---|---|---|
| GET | `/api/audit/batches` | `list_batches` |
| GET | `/api/audit/batches/{batch_id}` | `get_batch` |
| POST | `/api/audit/batches/{batch_id}/rollback` | `rollback_batch` |

## `collections.py` - Collections and question membership

| Method | Path | Handler |
|---|---|---|
| GET | `/api/collections/tree` | `get_tree` |
| POST | `/api/collections` | `create_collection` |
| POST | `/api/collections/batch-move` | `batch_move` |
| POST | `/api/collections/remove-questions` | `remove_questions` |
| GET | `/api/collections/questions/{question_id}` | `get_question_collections` |

## `export_package.py` - System package export

| Method | Path | Handler |
|---|---|---|
| GET | `/api/system/export-package` | `export_package` |

## `embedding_status.py` - Canonical question embedding coverage

| Method | Path | Handler |
|---|---|---|
| GET | `/embeddings/status` | `list_embedding_status` |

## `favorites.py` - Favorite groups and items

| Method | Path | Handler |
|---|---|---|
| GET | `/api/favorites/groups` | `list_groups` |
| POST | `/api/favorites/groups` | `create_group` |
| PUT | `/api/favorites/groups/{group_id}` | `update_group` |
| DELETE | `/api/favorites/groups/{group_id}` | `delete_group` |
| POST | `/api/favorites/assign` | `assign` |
| POST | `/api/favorites/batch-star` | `batch_star` |
| POST | `/api/favorites/remove` | `remove` |
| GET | `/api/favorites/items/{question_id}` | `get_item` |
| GET | `/api/favorites/items` | `list_items` |
| GET | `/api/favorites/ids` | `get_ids` |

## `image_management.py` - Question image cache and bindings

| Method | Path | Handler |
|---|---|---|
| GET | `/api/questions/images/cache` | `list_cache_images` |
| POST | `/api/questions/images/cache-upload` | `upload_cache_images` |
| GET | `/api/questions/{question_id}/images` | `list_images` |
| POST | `/api/questions/{question_id}/images` | `add_image` |
| POST | `/api/questions/{question_id}/images/from-cache` | `add_cached_image` |
| PUT | `/api/questions/{question_id}/images/{asset_id}/replace` | `replace_image` |
| PATCH | `/api/questions/{question_id}/images/{asset_id}` | `update_image` |
| DELETE | `/api/questions/{question_id}/images/{asset_id}` | `delete_image` |
| POST | `/api/questions/{question_id}/images/reorder` | `reorder_images` |
| GET | `/api/questions/{question_id}/images/validate` | `validate_images` |
| GET | `/api/questions/images/available` | `available_images` |

## `image_catalog.py` - Cross-question asset catalog

| Method | Path | Handler |
|---|---|---|
| GET | `/images` | `list_images` |

## `import_pipeline.py` - Import, recognition, review and durable jobs

| Method | Path | Handler |
|---|---|---|
| POST | `/api/import/batches` | `create_import_batch` |
| POST | `/api/import/batches/{batch_id}/pandoc` | `run_batch_pandoc` |
| POST | `/api/import/batches/{batch_id}/ai-clean` | `run_batch_ai_clean` |
| POST | `/api/import/batches/{batch_id}/ai-structure` | `structure_batch_questions` |
| POST | `/api/import/batches/{batch_id}/recognize` | `recognize_batch` |
| POST | `/api/import/batches/{batch_id}/pandoc-task` | `queue_batch_pandoc` |
| POST | `/api/import/batches/{batch_id}/ai-clean-task` | `queue_batch_ai_clean` |
| POST | `/api/import/batches/{batch_id}/ai-structure-task` | `queue_batch_ai_structure` |
| POST | `/api/import/batches/{batch_id}/recognize-task` | `queue_batch_recognition` |
| GET | `/api/import/task-queue/status` | `get_task_queue_status` |
| POST | `/api/import/batches/{batch_id}/extract-images` | `extract_batch_images` |
| POST | `/api/import/batches/{batch_id}/ai-refine` | `refine_batch_questions` |
| POST | `/api/import/batches/{batch_id}/draft-metadata` | `complete_draft_metadata` |
| GET | `/api/import/batches/{batch_id}` | `get_batch_status` |
| GET | `/api/import/batches` | `list_import_batches` |
| POST | `/api/import/batches/{batch_id}/retry` | `retry_import_batch` |
| POST | `/api/import/batches/{batch_id}/confirm` | `confirm_batch_questions` |
| POST | `/api/import/ai-generated-review` | `submit_ai_generated_review` |
| GET | `/api/import/review-tasks` | `list_review_tasks` |
| DELETE | `/api/import/review-tasks/{task_id}` | `delete_review_task` |
| POST | `/api/import/batches/{batch_id}/images` | `upload_batch_image` |
| GET | `/api/import/batches/{batch_id}/images` | `list_batch_images` |
| POST | `/api/import/upload` | `upload_import_file` |
| POST | `/api/import/convert` | `convert_document` |
| POST | `/api/import/clean` | `clean_document` |
| POST | `/api/import/parse` | `parse_structured_questions` |
| POST | `/api/import/ai-parse-document` | `ai_parse_document` |
| GET | `/api/import/tasks/{task_id}` | `get_import_task` |

## `lesson_documents.py` - Saved handouts and versions

| Method | Path | Handler |
|---|---|---|
| GET | `/api/lesson-documents/saved-handouts` | `list_handouts` |
| GET | `/api/lesson-documents/saved-handouts/{document_id}` | `get_handout` |
| POST | `/api/lesson-documents/saved-handouts` | `save_handout` |
| PATCH | `/api/lesson-documents/saved-handouts/{document_id}` | `rename_handout` |
| GET | `/api/lesson-documents/saved-handouts/{document_id}/versions` | `list_handout_versions` |
| POST | `/api/lesson-documents/saved-handouts/{document_id}/versions/{version}/restore` | `restore_handout_version` |

## `lesson_exports.py` - Word and PPTX exports

| Method | Path | Handler |
|---|---|---|
| POST | `/api/exports/word` | `export_word` |
| POST | `/api/exports/pptx` | `export_pptx` |

## MCP `export_questions_to_typst` - Read-only Typst question exports

- Input: up to 50 canonical question IDs, an optional title, `include_answers`, and `dry_run` (defaults to `true`).
- Output: a separate `data/exports/typst/<export-id>/` bundle containing only `questions-data.typ` and `image-map.typ`; no application template is copied or overridden.
- `questions-data.typ` provides `question-data`; `image-map.typ` provides `figure-paths` and `figures-for(question_id)`. Any user-owned template can import these values and decide how to render each question or image.
- Gallery safety: the tool reads only managed assets. It does not copy, move, rename, compress, or delete any gallery file; unavailable images are listed in the manifest.

## `knowledge_points.py` - Canonical knowledge-point catalog and aggregates

| Method | Path | Handler |
|---|---|---|
| GET | `/knowledge-points` | `list_knowledge_points` |
| GET | `/knowledge-points/counts` | `knowledge_point_counts` |
| GET | `/questions/{question_id}/knowledge-points` | `list_question_knowledge_points` |
| PUT | `/questions/{question_id}/knowledge-points` | `replace_question_knowledge_points` |
| PUT | `/questions/{question_id}/knowledge-points/{rank}` | `upsert_question_knowledge_point` |
| DELETE | `/questions/{question_id}/knowledge-points/{rank}` | `delete_question_knowledge_point` |

## `mcp.py` - MCP/model configuration and capabilities

| Method | Path | Handler |
|---|---|---|
| GET | `/api/mcp/status` | `get_status` |
| GET | `/api/mcp/config` | `get_config` |
| POST | `/api/mcp/config` | `update_config` |
| POST | `/api/mcp/test-connection` | `test_connection` |
| POST | `/api/mcp/chat-test` | `chat_test` |
| POST | `/api/mcp/refine-question-format` | `refine_question_format` |
| POST | `/api/mcp/parse-document` | `parse_document` |
| POST | `/api/mcp/detect-question-regions` | `detect_question_regions` |
| POST | `/api/mcp/parse-question-region` | `parse_question_region` |
| POST | `/api/mcp/generate-analysis` | `generate_analysis` |
| POST | `/api/mcp/generate-knowledge` | `generate_knowledge` |
| POST | `/api/mcp/generate-metadata` | `generate_metadata` |

## `metadata_batch.py` - Batch metadata changes

| Method | Path | Handler |
|---|---|---|
| POST | `/api/questions/batch-metadata` | `batch_metadata` |

## `mistake.py` - Mistake marking

| Method | Path | Handler |
|---|---|---|
| POST | `/api/questions/{question_id}/mistake/mark` | `mark_mistake` |
| POST | `/api/questions/{question_id}/mistake/unmark` | `unmark_mistake` |
| POST | `/api/questions/mistake/batch-mark` | `batch_mark` |
| POST | `/api/questions/mistake/batch-unmark` | `batch_unmark` |
| GET | `/api/questions/mistakes` | `list_mistakes` |
| GET | `/api/questions/mistakes/count` | `count_mistakes` |

## `paper_drafts.py` - Paper drafts

| Method | Path | Handler |
|---|---|---|
| GET | `/api/paper-drafts` | `list_drafts` |
| GET | `/api/paper-drafts/latest` | `get_latest_draft` |
| GET | `/api/paper-drafts/{draft_id}` | `get_draft` |
| POST | `/api/paper-drafts` | `save_draft` |
| DELETE | `/api/paper-drafts/{draft_id}` | `delete_draft` |

## `papers.py` - Canonical paper catalog and details

| Method | Path | Handler |
|---|---|---|
| GET | `/papers` | `list_papers` |
| GET | `/papers/{paper_id}` | `get_paper` |
| GET | `/papers/{paper_id}/questions` | `list_paper_questions` |

## `processing_runs.py` - Historical processing-run read API

| Method | Path | Handler |
|---|---|---|
| GET | `/processing-runs` | `list_processing_runs` |

## `question_search.py` - Question search and controlled writes

| Method | Path | Handler |
|---|---|---|
| GET | `/search/questions` | `search_questions` |
| GET | `/filters/facets` | `get_facets` |
| POST | `/api/questions/batch-get` | `batch_get_questions` |
| POST | `/api/questions/batch-delete` | `batch_delete_questions` |
| POST | `/api/questions/{question_id}/return-to-review` | `return_question_to_review` |

## `question_imports.py` - Structured external question import

| Method | Path | Handler |
|---|---|---|
| POST | `/questions/import` | `import_question` |

## `question_updates.py` - Canonical question edit with field merging

| Method | Path | Handler |
|---|---|---|
| PUT | `/questions/{question_id}` | `update_question` |

## `question_reviews.py` - Canonical review actions and review-workspace history

| Method | Path | Handler |
|---|---|---|
| POST | `/questions/{question_id}/review` | `review_question` |
| POST | `/questions/{question_id}/propose-fix` | `propose_fix` |
| POST | `/questions/{question_id}/report-issue` | `report_issue` |
| GET | `/questions/{question_id}/review-history` | `review_history` |
| GET | `/review-queue/pending-fixes` | `list_pending_fixes` |
| GET | `/review-queue/rejected` | `list_rejected_questions` |
| GET | `/review-queue/{review_id}` | `get_fix_detail` |
| POST | `/review-queue/{review_id}/decide` | `decide_fix` |

## `question_details.py` - Canonical question detail read model

| Method | Path | Handler |
|---|---|---|
| GET | `/questions/{question_id}` | `get_question` |
| GET | `/questions/{question_id}/assets` | `list_question_assets` |

## `question_versions.py` - Canonical question version history and rollback

| Method | Path | Handler |
|---|---|---|
| GET | `/questions/{question_id}/versions` | `list_question_versions` |
| GET | `/questions/{question_id}/versions/{version_id}` | `get_question_version` |
| POST | `/questions/{question_id}/versions/{version_id}/rollback` | `rollback_question_version` |

## `question_stats.py` - Canonical question status aggregates

| Method | Path | Handler |
|---|---|---|
| GET | `/stats/questions` | `question_stats` |

## `question_variants.py` - Question variant generation

| Method | Path | Handler |
|---|---|---|
| POST | `/api/ai/question-variants/generate` | `generate_question_variants` |

## `restore_package.py` - System package restore

| Method | Path | Handler |
|---|---|---|
| POST | `/api/system/restore-package` | `restore_package` |

## `review_queue.py` - Review queue

| Method | Path | Handler |
|---|---|---|
| GET | `/review-queue` | `list_review_queue` |
| GET | `/api/review-queue` | `list_review_queue_api` |

## `review_save.py` - Review drafts and submission

| Method | Path | Handler |
|---|---|---|
| GET | `/api/review/drafts/{task_id}` | `get_review_draft` |
| PUT | `/api/review/drafts/{task_id}` | `save_review_draft` |
| GET | `/api/review/drafts/{task_id}/versions` | `list_review_draft_versions` |
| DELETE | `/api/review/drafts/{task_id}` | `delete_review_draft` |
| POST | `/api/review/drafts/{task_id}/restore` | `restore_review_draft` |
| POST | `/api/review/save` | `save_reviewed` |
| POST | `/api/review/save-knowledge` | `save_reviewed_knowledge` |

## `similar_questions.py` - Similar-question search

| Method | Path | Handler |
|---|---|---|
| GET | `/api/questions/{question_id}/similar` | `find_similar` |

## `system_status.py` - Database status

| Method | Path | Handler |
|---|---|---|
| GET | `/api/system/db-status` | `db_status` |

## `tasks.py` - Task center and result downloads

| Method | Path | Handler |
|---|---|---|
| GET | `/api/tasks` | `list_tasks` |
| GET | `/api/tasks/health` | `get_task_queue_health` |
| GET | `/api/tasks/{task_id}` | `get_task` |
| POST | `/api/tasks/{task_id}/retry` | `retry_task` |
| POST | `/api/tasks/{task_id}/cancel` | `cancel_task` |
| GET | `/api/tasks/{task_id}/download` | `download_task_result` |

## `lesson_reflections.py` - Lesson reflections; second prefix is MCP mirror

| Method | Path | Handler |
|---|---|---|
| GET | `/api/lesson-reflections` | `list_reflections` |
| GET | `/api/lesson-reflections/{reflection_id}` | `get_reflection` |
| POST | `/api/lesson-reflections` | `save_reflection` |
| GET | `/api/mcp/lesson-reflections` | `list_reflections` |
| GET | `/api/mcp/lesson-reflections/{reflection_id}` | `get_reflection` |
| POST | `/api/mcp/lesson-reflections` | `save_reflection` |

## `teaching_projects.py` - Teaching projects; second prefix is MCP mirror

| Method | Path | Handler |
|---|---|---|
| GET | `/api/teaching-projects` | `list_projects` |
| GET | `/api/teaching-projects/{project_id}` | `get_project` |
| POST | `/api/teaching-projects` | `save_project` |
| POST | `/api/teaching-projects/{project_id}/archive` | `archive_project` |
| POST | `/api/teaching-projects/{project_id}/duplicate` | `duplicate_project` |
| GET | `/api/mcp/teaching-projects` | `list_projects` |
| GET | `/api/mcp/teaching-projects/{project_id}` | `get_project` |
| POST | `/api/mcp/teaching-projects` | `save_project` |
| POST | `/api/mcp/teaching-projects/{project_id}/archive` | `archive_project` |
| POST | `/api/mcp/teaching-projects/{project_id}/duplicate` | `duplicate_project` |

## Business flows

1. **Import to canonical bank**: `/api/import/*` creates a batch, converts/cleans/structures/recognizes it, sends review tasks, and confirms approved questions into the canonical bank. Prefer the task endpoints for long-running stages.
2. **Question governance**: `/search/questions` finds questions; image, annotation, favorite, collection, mistake, and metadata endpoints enrich governance. `return-to-review` moves a canonical question back into the review workflow.
3. **Teaching production**: paper drafts, saved handouts, and teaching projects create an immutable export request; `/api/tasks/{task_id}` supplies status and download.
4. **AI and MCP**: `/api/mcp/*` is the model-capability gateway, while `/api/ai/*` owns business results. MCP mirrors reuse the same service and must not fork business logic.

## Change rules

- Before deleting an endpoint, remove every frontend/MCP/test caller and retain an explicit migration note or redirect for one release cycle.
- Canonical-bank writes must use controlled services and change audit; never mix canonical and review repositories.
- Each new router needs success, validation, failure/retry, and boundary tests.
- Update this catalog whenever `ApplicationContainer.routers()` changes.
