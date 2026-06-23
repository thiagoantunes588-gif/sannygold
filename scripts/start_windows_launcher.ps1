param(
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "windows-launcher.log"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LauncherScript = Join-Path $ProjectRoot "scripts\sannygold_launcher.py"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-LauncherLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Encoding UTF8 -Value "[$timestamp] $Message"
}

try {
    if (-not (Test-Path $VenvPython)) {
        throw "Ambiente virtual nao encontrado em .venv. Execute scripts\install_windows_launcher.ps1 primeiro."
    }
    if (-not (Test-Path $LauncherScript)) {
        throw "Launcher Python nao encontrado: $LauncherScript"
    }

    Write-LauncherLog "Abrindo launcher com $VenvPython"
    & $VenvPython $LauncherScript *>> $LogFile
}
catch {
    Write-LauncherLog "Erro: $($_.Exception.Message)"
    Write-Host "Nao foi possivel abrir o SannyGold Sistema." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Veja o log em: $LogFile"
    if (-not $NoPause) {
        Read-Host "Pressione Enter para fechar"
    }
    exit 1
}
