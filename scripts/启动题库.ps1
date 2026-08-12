[CmdletBinding()]
param(
    [switch]$Silent
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ApiRoot = Join-Path $ProjectRoot 'apps\api'
$ApiSource = Join-Path $ApiRoot 'src'
$WebRoot = Join-Path $ProjectRoot 'apps\web'
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$ApiLog = Join-Path $ProjectRoot '.server-logs\api.log'
$ApiErrorLog = Join-Path $ProjectRoot '.server-logs\api-error.log'
$WebLog = Join-Path $ProjectRoot '.server-logs\web.log'
$WebErrorLog = Join-Path $ProjectRoot '.server-logs\web-error.log'
$ApiUrl = 'http://127.0.0.1:8000/health'
$WebUrl = 'http://127.0.0.1:5173'

function Write-Status([string]$Message) {
    Write-Host "[Physics Vault] $Message"
}

function Test-LocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        return $task.Wait(700) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-ForUrl([string]$Url, [int]$Seconds, [string]$Name) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)

    throw "$Name 在 $Seconds 秒内未就绪。请查看 .server-logs 中的日志。"
}

function Get-BootstrapPython {
    foreach ($candidate in @('py.exe', 'python.exe')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw '未找到可用于创建项目专属 Python 环境的 Python。请安装 Python 3.12 后重试。'
}

function Ensure-BackendRuntime {
    New-Item -ItemType Directory -Force -Path (Split-Path $ApiLog) | Out-Null
    $runtimeHealthy = $false
    if (Test-Path -LiteralPath $VenvPython) {
        & $VenvPython -c "import fastapi, uvicorn" 2>$null
        $runtimeHealthy = $LASTEXITCODE -eq 0
    }

    if (-not $runtimeHealthy) {
        if (-not (Test-Path -LiteralPath $VenvPython)) {
            Write-Status '正在创建项目专属 Python 环境…'
            $bootstrap = Get-BootstrapPython
            if ((Split-Path $bootstrap -Leaf) -ieq 'py.exe') {
                & $bootstrap -3 -m venv (Join-Path $ProjectRoot '.venv')
            }
            else {
                & $bootstrap -m venv (Join-Path $ProjectRoot '.venv')
            }
            if ($LASTEXITCODE -ne 0) { throw '创建项目专属 Python 环境失败。' }
        }

        Write-Status '正在补齐后端依赖（仅写入项目 .venv）…'
        & $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $ApiRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw '后端依赖安装失败。请检查网络或 .server-logs。' }
    }
}

function Ensure-FrontendRuntime {
    $nodeModules = Join-Path $WebRoot 'node_modules'
    if (-not (Test-Path -LiteralPath $nodeModules)) {
        $npm = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
        if (-not $npm) { throw '未找到 npm。请安装 Node.js LTS 后重试。' }
        Write-Status '正在安装前端依赖（首次启动仅需一次）…'
        Push-Location $WebRoot
        try {
            & $npm.Source ci
            if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败。请检查网络后重试。' }
        }
        finally {
            Pop-Location
        }
    }
}

try {
    Set-Location $ProjectRoot
    Ensure-BackendRuntime
    Ensure-FrontendRuntime

    if (Test-LocalPort 8000) {
        try {
            Wait-ForUrl $ApiUrl 5 '已占用 8000 端口的服务'
            Write-Status '后端已在运行，未重复启动。'
        }
        catch {
            throw '8000 端口已被占用，但该服务不是可用的 Physics Vault 后端。请关闭占用端口的程序后重试。'
        }
    }
    else {
        Write-Status '正在启动后端…'
        $previousPythonPath = $env:PYTHONPATH
        $env:PYTHONPATH = $ApiSource
        try {
            Start-Process -FilePath $VenvPython -ArgumentList @('-m', 'uvicorn', 'physics_vault_api.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $ApiLog -RedirectStandardError $ApiErrorLog | Out-Null
        }
        finally {
            $env:PYTHONPATH = $previousPythonPath
        }
        Wait-ForUrl $ApiUrl 45 'Physics Vault 后端'
    }

    if (Test-LocalPort 5173) {
        Wait-ForUrl $WebUrl 5 '已占用 5173 端口的服务'
        Write-Status '前端已在运行，未重复启动。'
    }
    else {
        Write-Status '正在启动前端…'
        Start-Process -FilePath $env:ComSpec -ArgumentList @('/d', '/c', 'npm.cmd run dev') -WorkingDirectory $WebRoot -WindowStyle Hidden -RedirectStandardOutput $WebLog -RedirectStandardError $WebErrorLog | Out-Null
        Wait-ForUrl $WebUrl 45 'Physics Vault 前端'
    }

    Write-Status "启动完成，正在打开 $WebUrl"
    Start-Process $WebUrl
}
catch {
    $failureMessage = "启动失败：$($_.Exception.Message)`n`n请检查：$ProjectRoot\.server-logs"
    if ($Silent) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show($failureMessage, 'Physics Vault 启动失败', 'OK', 'Error') | Out-Null
    }
    else {
        Write-Host "`n$failureMessage" -ForegroundColor Red
        Read-Host '按 Enter 关闭此窗口'
    }
    exit 1
}
