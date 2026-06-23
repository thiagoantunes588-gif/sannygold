param(
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
$EnvFile = Join-Path $ProjectRoot ".env.local"
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "windows-launcher.log"
$DropboxRoot = Join-Path $env:USERPROFILE "Dropbox"
$DropboxBackupDir = Join-Path $DropboxRoot "Sistema SannyGold\Backups"
$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "SannyGold Sistema.lnk"
$LauncherPs1 = Join-Path $ProjectRoot "scripts\start_windows_launcher.ps1"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-InstallerLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Encoding UTF8 -Value "[$timestamp] $Message"
}

function Test-PathInside {
    param(
        [string]$ChildPath,
        [string]$ParentPath
    )

    if ([string]::IsNullOrWhiteSpace($ChildPath) -or [string]::IsNullOrWhiteSpace($ParentPath)) {
        return $false
    }

    $childFull = [System.IO.Path]::GetFullPath($ChildPath).TrimEnd("\", "/")
    $parentFull = [System.IO.Path]::GetFullPath($ParentPath).TrimEnd("\", "/")
    $isSamePath = $childFull.Equals($parentFull, [System.StringComparison]::OrdinalIgnoreCase)
    $isChildPath = $childFull.StartsWith($parentFull + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
    return ($isSamePath -or $isChildPath)
}

function Get-SystemPythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    throw "Python nao encontrado. Instale Python 3 para Windows, marque 'Add python.exe to PATH', feche o PowerShell e rode este instalador novamente."
}

function Invoke-Python {
    param(
        [string[]]$PythonCommand,
        [string[]]$Arguments
    )

    $exe = $PythonCommand[0]
    $baseArgs = @()
    if ($PythonCommand.Count -gt 1) {
        $baseArgs = $PythonCommand[1..($PythonCommand.Count - 1)]
    }
    & $exe @baseArgs @Arguments
}

try {
    Write-InstallerLog "Instalador Windows iniciado em $ProjectRoot"
    if (Test-PathInside -ChildPath $ProjectRoot -ParentPath $DropboxRoot) {
        throw "Configuracao insegura: a pasta inteira do sistema nao pode ficar dentro do Dropbox. Use Dropbox apenas para backups .zip."
    }
    foreach ($folder in @("data", "uploads", "preview", "tmp", "logs", "backups")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $folder) | Out-Null
    }

    $PythonCommand = Get-SystemPythonCommand

    if (-not (Test-Path $VenvPython)) {
        Write-Host "Criando ambiente virtual .venv..."
        Invoke-Python -PythonCommand $PythonCommand -Arguments @("-m", "venv", $VenvDir)
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao criar .venv. Verifique a instalacao do Python."
        }
    }

    Write-Host "Instalando dependencias..."
    & $VenvPython -m pip install -r $RequirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar requirements.txt."
    }

    if (-not (Test-Path $DropboxRoot)) {
        Write-Warning "Dropbox nao encontrado em $DropboxRoot. A pasta de backup sera criada, mas confirme se o Dropbox esta instalado e sincronizando."
        Write-InstallerLog "Dropbox nao encontrado em $DropboxRoot"
    }
    New-Item -ItemType Directory -Force -Path $DropboxBackupDir | Out-Null

    if (-not (Test-Path $EnvFile)) {
        $secretKey = (& $VenvPython -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
        $envValues = [ordered]@{
            "SANNYGOLD_ENV" = "local"
            "SANNYGOLD_SECRET_KEY" = $secretKey
            "SANNYGOLD_ADMIN_EMAIL" = "contato@sannygold.com"
            "SANNYGOLD_ADMIN_PASSWORD" = "troque-esta-senha"
            "SANNYGOLD_ADMIN_NAME" = "Administrador SannyGold"
            "ROTAFLOW_STORAGE_DIR" = $ProjectRoot
            "SANNYGOLD_SQLITE_PATH" = (Join-Path $ProjectRoot "data\sannygold.db")
            "SANNYGOLD_STORAGE_BACKEND" = "sqlite"
            "SANNYGOLD_SQLITE_MIRROR_JSON" = "1"
            "DROPBOX_BACKUP_DIR" = $DropboxBackupDir
            "SANNYGOLD_BACKUP_RETENTION_LIMIT" = "30"
            "SANNYGOLD_DROPBOX_BACKUP_RETENTION_LIMIT" = "30"
            "PORT" = "5007"
            "FLASK_HOST" = "0.0.0.0"
            "FLASK_DEBUG" = "0"
            "SANNYGOLD_SESSION_COOKIE_SECURE" = "0"
            "SANNYGOLD_CSRF_DISABLED" = "0"
        }
        $envValues.GetEnumerator() |
            ForEach-Object { "$($_.Key)=$($_.Value)" } |
            Set-Content -Path $EnvFile -Encoding UTF8
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-ExecutionPolicy Bypass -File `"$LauncherPs1`""
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.IconLocation = "powershell.exe,0"
    $shortcut.Description = "SannyGold Sistema"
    $shortcut.Save()

    Write-InstallerLog "Atalho criado em $ShortcutPath"
    Write-Host "Instalacao concluida."
    Write-Host "Atalho criado: $ShortcutPath"
    Write-Host "Backups Dropbox: $DropboxBackupDir"
    Write-Host "Dados locais ficam em: $(Join-Path $ProjectRoot 'data')"
    Write-Host "Nao coloque data, uploads ou sannygold.db dentro do Dropbox. Dropbox deve receber apenas .zip de backup."
}
catch {
    Write-InstallerLog "Erro: $($_.Exception.Message)"
    Write-Host "Nao foi possivel instalar o launcher Windows." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Veja o log em: $LogFile"
    if (-not $NoPause) {
        Read-Host "Pressione Enter para fechar"
    }
    exit 1
}

if (-not $NoPause) {
    Read-Host "Pressione Enter para fechar"
}
