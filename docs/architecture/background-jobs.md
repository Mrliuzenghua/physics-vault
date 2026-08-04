# Background jobs

Physics Vault uses Dramatiq with Redis for long-running import and Office export stages. Task state and results stay in the existing SQLite `import_pipeline_tasks` table; Redis only transports messages.

Covered stages:

- Word/Markdown conversion and media extraction
- AI-assisted Markdown cleaning
- question structuring and AI refinement
- automatic Word/PDF/image recognition
- immutable-snapshot Word and PPTX export

## Local synchronous mode

The queue is disabled unless `PHYSICS_TASK_QUEUE_ENABLED=true` or `PHYSICS_TASK_BROKER_URL` is explicitly set. In that mode the same task records are created, but the API process executes them immediately. This keeps tests and simple local development self-contained.

## Redis and worker mode

Start Redis, then set:

```powershell
$env:PHYSICS_TASK_QUEUE_ENABLED = "true"
$env:PHYSICS_TASK_BROKER_URL = "redis://127.0.0.1:6379/0"
$env:PHYSICS_TASK_QUEUE_NAMESPACE = "physics-vault"
$env:PHYSICS_TASK_MAX_RETRIES = "4"
$env:PHYSICS_TASK_TIME_LIMIT_MS = "1800000"
```

Start the API and worker with the same environment. From `apps/api`:

```powershell
python -m dramatiq physics_vault_api.tasks.import_pipeline physics_vault_api.tasks.lesson_exports --processes 1 --threads 4 --use-spawn
```

The worker uses a lightweight `WorkerContainer`; it only builds the import pipeline, MCP gateway, and durable task repository. It does not construct search, review, asset, or other Web application services.

Retry count, exponential backoff and execution timeout are shared by the API and worker through environment variables:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `PHYSICS_TASK_MAX_RETRIES` | `4` | retries after the first attempt |
| `PHYSICS_TASK_MIN_BACKOFF_MS` | `5000` | initial retry backoff |
| `PHYSICS_TASK_MAX_BACKOFF_MS` | `300000` | maximum retry backoff |
| `PHYSICS_TASK_TIME_LIMIT_MS` | `1800000` | actor execution limit |
| `PHYSICS_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS` | `10` | worker heartbeat interval |
| `PHYSICS_TASK_WORKER_HEARTBEAT_TTL_SECONDS` | `35` | heartbeat expiry |
| `PHYSICS_TASK_STALE_AFTER_SECONDS` | `1900` | age at which active SQLite tasks are recovered |

Network timeouts, model rate limits, Redis errors, and temporary provider failures use exponential retry. Corrupt files, unsupported formats, missing files, and invalid parameters fail without retry. The last failed attempt is always persisted to SQLite; a startup recovery pass moves abandoned `running` tasks to `retrying`, or to `failed` when their attempt limit is exhausted.

The API exposes:

- `GET /api/import/task-queue/status` for the legacy configuration summary.
- `GET /api/tasks/health` for queue mode, Redis reachability, latest worker heartbeat, queue backlog, and the most recent durable task error.
- `GET /api/import/tasks/{task_id}` for durable polling.

Dramatiq's result backend is intentionally not enabled because SQLite is the system of record. In synchronous mode the health endpoint reports Redis and worker monitoring as disabled and does not contact Redis.

## MCP task tools

The `physics_vault` MCP server exposes the same application services used by the API; it never edits the task tables directly:

- `submit_import_job` and `submit_ai_clean_job`
- `submit_word_export_job` and `submit_pptx_export_job`
- `get_job_status` and paginated `list_jobs`
- `retry_job` and `cancel_job`

Query tools are read-only. Retry and cancellation first return a compact action preview and only execute when called again with `confirmed=true` after explicit user confirmation. Every successful MCP write records a separate `task_action_audit` row containing the action, source, session ID, operator, confirmation flag, and a small structured summary. MCP responses contain only task metadata, compact result/error summaries, and a download URL when an artifact is ready; immutable lesson snapshots and full documents are not returned through MCP.
