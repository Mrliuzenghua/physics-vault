from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import time
from typing import Any

from openai import RateLimitError

from ..database import connect_db
from .embedding_runtime import (
    build_question_embedding_text, compute_content_hash, create_processing_run,
    finish_processing_run, resolve_embedding_client, resolve_embedding_model,
    truncate_text, upsert_question_embedding,
)
from ..paths import default_db_path
from ..schemas.embedding_builds import EmbeddingBuildRequest, EmbeddingBuildResponse


class EmbeddingBuildService:
    def build(self, payload: EmbeddingBuildRequest) -> EmbeddingBuildResponse:
        provider = payload.provider.strip().lower()
        model_name = resolve_embedding_model(provider, payload.model)
        client = None if payload.dry_run else resolve_embedding_client(provider, payload.base_url)
        sql = """SELECT q.question_id, q.primary_paper_id AS paper_id, q.canonical_title,
            q.module, q.topic2, q.topic3, q.difficulty, q.question_type, qti.stem_text,
            (SELECT GROUP_CONCAT(ranked.topic3_name, '、') FROM (
                SELECT kp.topic3_name
                FROM question_knowledge_points qkp
                INNER JOIN knowledge_points kp ON kp.topic3_id = qkp.topic3_id
                WHERE qkp.question_id = q.question_id
                ORDER BY qkp.rank, qkp.topic3_id
                LIMIT 3
            ) ranked) AS structured_topic3,
            q.vault_markdown_path FROM questions q INNER JOIN question_text_index qti
            ON qti.question_id=q.question_id WHERE qti.stem_text IS NOT NULL AND TRIM(qti.stem_text) != ''"""
        params: list[Any] = []
        if payload.question_ids:
            sql += " AND q.question_id IN (" + ",".join("?" for _ in payload.question_ids) + ")"
            params.extend(payload.question_ids)
        if payload.since_question_id:
            sql += " AND q.question_id >= ?"; params.append(payload.since_question_id)
        sql += " ORDER BY q.question_id"
        if payload.limit:
            sql += " LIMIT ?"; params.append(payload.limit)
        with closing(connect_db(default_db_path())) as connection:
            rows = connection.execute(sql, params).fetchall()
            existing = {row["owner_id"]: (row["content_hash"], row["status"]) for row in connection.execute(
                "SELECT owner_id, content_hash, status FROM embeddings WHERE owner_type='question' AND model_name=? AND COALESCE(model_version,'')=COALESCE(?, '') AND vector_type=?",
                (model_name, payload.model_version, payload.vector_type)).fetchall()}
            summary = {"provider": provider, "model_name": model_name, "model_version": payload.model_version, "vector_type": payload.vector_type, "candidate_count": len(rows), "concurrency": payload.concurrency, "dry_run": payload.dry_run}
            run_id = create_processing_run(connection, summary)
            prepared = []
            skipped = 0
            effective_max_tokens = min(payload.max_tokens, 2048) if provider == "alibaba" else payload.max_tokens
            for row in rows:
                text, _ = truncate_text(build_question_embedding_text(row), model_name, effective_max_tokens)
                content_hash = compute_content_hash(text)
                existing_hash, existing_status = existing.get(row["question_id"], (None, None))
                if not payload.force and existing_hash == content_hash:
                    if existing_status != "ready" and not payload.dry_run:
                        connection.execute(
                            """
                            UPDATE embeddings
                            SET status = 'ready', updated_at = CURRENT_TIMESTAMP
                            WHERE owner_type = 'question' AND owner_id = ?
                              AND model_name = ? AND vector_type = ?
                              AND COALESCE(model_version, '') = COALESCE(?, '')
                            """,
                            (row["question_id"], model_name, payload.vector_type, payload.model_version),
                        )
                    skipped += 1; continue
                prepared.append({"question_id": row["question_id"], "text": text, "content_hash": content_hash})
            connection.commit()
            embedded = 0
            executor: ThreadPoolExecutor | None = None
            try:
                effective_batch_size = min(payload.batch_size, 10) if provider == "alibaba" else payload.batch_size
                batches = [
                    prepared[start:start + effective_batch_size]
                    for start in range(0, len(prepared), effective_batch_size)
                ]

                def embed_batch(batch: list[dict[str, Any]]) -> list[list[float]]:
                    response = None
                    for attempt in range(payload.max_retries + 1):
                        try:
                            response = client.embeddings.create(
                                model=model_name,
                                input=[item["text"] for item in batch],
                                encoding_format="float",
                                **({"dimensions": payload.dimensions} if payload.dimensions else {}),
                            )
                            break
                        except RateLimitError:
                            if attempt >= payload.max_retries:
                                raise
                            time.sleep(min(5 * (2 ** attempt), 30))
                    if response is None:
                        raise RuntimeError("embedding provider returned no response")
                    vectors = [item.embedding for item in response.data]
                    if len(vectors) != len(batch):
                        raise RuntimeError(
                            f"embedding response count mismatch: expected {len(batch)}, got {len(vectors)}"
                        )
                    return vectors

                if payload.dry_run:
                    embedded_batches: Any = []
                elif payload.concurrency == 1:
                    embedded_batches = map(embed_batch, batches)
                else:
                    executor = ThreadPoolExecutor(max_workers=payload.concurrency)
                    embedded_batches = executor.map(embed_batch, batches)

                for batch, vectors in zip(batches, embedded_batches):
                    for index, item in enumerate(batch):
                        upsert_question_embedding(connection, question_id=item["question_id"], vector_type=payload.vector_type, model_name=model_name, model_version=payload.model_version, dimensions=len(vectors[index]), content_hash=item["content_hash"], vector=vectors[index]); embedded += 1
                    connection.commit()
                if not payload.dry_run and payload.concurrency > 1:
                    executor.shutdown(wait=True)
            except Exception as exc:
                if executor is not None:
                    executor.shutdown(wait=True, cancel_futures=True)
                connection.rollback(); finish_processing_run(connection, run_id, "failed", {**summary, "embedded_count": embedded, "error": str(exc)}); raise RuntimeError(str(exc)) from exc
            finish_processing_run(connection, run_id, "completed", {**summary, "processed_count": len(prepared), "embedded_count": embedded, "skipped_count": skipped})
        return EmbeddingBuildResponse(run_id=run_id, provider=provider, model_name=model_name, vector_type=payload.vector_type, processed_count=len(prepared), embedded_count=embedded, skipped_count=skipped, failed_count=0, dry_run=payload.dry_run)
