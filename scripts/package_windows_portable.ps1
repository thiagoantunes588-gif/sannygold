param(
    [switch]$SkipAppBuild
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$PackageScript = Join-Path $ProjectRoot "scripts\package_windows_source_portable.py"
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "build-windows.log"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-BuildLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Encoding UTF8 -Value "[$timestamp] $Message"
}

function Get-SystemPythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    if (Get-Command python3 -ErrorAction SilentlyContinue) {
        return @("python3")
    }
    throw "Python 3 nao encontrado. Instale Python 3 e tente novamente."
}

try {
    Write-BuildLog "Geracao do pacote portatil Windows por codigo-fonte iniciada"
    if (-not (Test-Path $PackageScript)) {
        throw "Script de empacotamento portatil nao encontrado: $PackageScript"
    }

    $pythonCommand = Get-SystemPythonCommand
    $exe = $pythonCommand[0]
    $baseArgs = @()
    if ($pythonCommand.Count -gt 1) {
        $baseArgs = $pythonCommand[1..($pythonCommand.Count - 1)]
    }
    & $exe @baseArgs $PackageScript
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao gerar SannyGold-Sistema-Windows-Portable.zip."
    }
    Write-BuildLog "Pacote portatil Windows por codigo-fonte gerado com sucesso"
}
catch {
    Write-BuildLog "Erro no pacote portatil: $($_.Exception.Message)"
    Write-Host "Falha ao gerar o pacote portatil Windows." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Veja o log em: $LogFile"
    exit 1
}
