$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ApiRoot = Join-Path $ProjectRoot "apps\api"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

if (-not $env:PHYSICS_TASK_BROKER_URL) {
    $env:PHYSICS_TASK_BROKER_URL = "redis://127.0.0.1:6379/0"
}
if (-not $env:PHYSICS_TASK_QUEUE_NAMESPACE) { $env:PHYSICS_TASK_QUEUE_NAMESPACE = "physics-vault" }
if (-not $env:PHYSICS_TASK_QUEUE_NAME) { $env:PHYSICS_TASK_QUEUE_NAME = "imports" }
if (-not $env:PHYSICS_TASK_CONTROL_QUEUE_NAME) { $env:PHYSICS_TASK_CONTROL_QUEUE_NAME = "import-control" }
if (-not $env:PHYSICS_TASK_MAX_RETRIES) { $env:PHYSICS_TASK_MAX_RETRIES = "4" }
if (-not $env:PHYSICS_TASK_MIN_BACKOFF_MS) { $env:PHYSICS_TASK_MIN_BACKOFF_MS = "5000" }
if (-not $env:PHYSICS_TASK_MAX_BACKOFF_MS) { $env:PHYSICS_TASK_MAX_BACKOFF_MS = "300000" }
if (-not $env:PHYSICS_TASK_TIME_LIMIT_MS) { $env:PHYSICS_TASK_TIME_LIMIT_MS = "1800000" }
$env:PHYSICS_TASK_QUEUE_ENABLED = "true"
$env:PYTHONPATH = Join-Path $ApiRoot "src"

Set-Location $ApiRoot
& $Python -m dramatiq physics_vault_api.tasks.import_pipeline physics_vault_api.tasks.lesson_exports --processes 1 --threads 4 --use-spawn
