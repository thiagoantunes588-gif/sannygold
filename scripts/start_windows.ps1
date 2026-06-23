param(
    [switch]$SetupOnly
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$EnvFile = Join-Path $ProjectRoot ".env.local"
$DefaultPort = "5007"
$DefaultHost = "0.0.0.0"
$DropboxBackupDir = Join-Path $env:USERPROFILE "Dropbox\Sistema SannyGold\Backups"

Set-Location $ProjectRoot

foreach ($folder in @("data", "uploads", "preview", "tmp", "logs", "backups")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $folder) | Out-Null
}

function Get-SystemPythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    throw "Python 3 nao encontrado. Instale Python 3 e tente novamente."
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

function Import-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    foreach ($line in Get-Content -Path $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        $parts = $trimmed.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Set-EnvDefault {
    param(
        [string]$Name,
        [string]$Value
    )

    $current = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($current)) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
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

function Assert-NotInsideDropbox {
    param(
        [string]$Label,
        [string]$PathToCheck,
        [string]$DropboxRoot
    )

    if (Test-PathInside -ChildPath $PathToCheck -ParentPath $DropboxRoot) {
        throw "Configuracao insegura: $Label nao pode ficar dentro do Dropbox. Use Dropbox apenas para backups .zip."
    }
}

function Get-LocalWifiIp {
    try {
        $addresses = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName())
        $ip = $addresses |
            Where-Object {
                $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
                -not [System.Net.IPAddress]::IsLoopback($_) -and
                -not $_.IPAddressToString.StartsWith("169.254.")
            } |
            Select-Object -First 1
        if ($ip) {
            return $ip.IPAddressToString
        }
    }
    catch {
        return $null
    }
    return $null
}

$PythonCommand = Get-SystemPythonCommand

if (-not (Test-Path $EnvFile)) {
    $secretKey = (Invoke-Python -PythonCommand $PythonCommand -Arguments @("-c", "import secrets; print(secrets.token_urlsafe(48))")).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($secretKey)) {
        throw "Nao foi possivel gerar SANNYGOLD_SECRET_KEY com Python."
    }

    $envDefaults = [ordered]@{
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
        "PORT" = $DefaultPort
        "FLASK_HOST" = $DefaultHost
        "FLASK_DEBUG" = "0"
        "SANNYGOLD_SESSION_COOKIE_SECURE" = "0"
        "SANNYGOLD_CSRF_DISABLED" = "0"
    }

    $envDefaults.GetEnumerator() |
        ForEach-Object { "$($_.Key)=$($_.Value)" } |
        Set-Content -Path $EnvFile -Encoding UTF8
}

Import-EnvFile -Path $EnvFile

Set-EnvDefault -Name "SANNYGOLD_ENV" -Value "local"
Set-EnvDefault -Name "ROTAFLOW_STORAGE_DIR" -Value $ProjectRoot
Set-EnvDefault -Name "SANNYGOLD_SQLITE_PATH" -Value (Join-Path $ProjectRoot "data\sannygold.db")
Set-EnvDefault -Name "SANNYGOLD_STORAGE_BACKEND" -Value "sqlite"
Set-EnvDefault -Name "SANNYGOLD_SQLITE_MIRROR_JSON" -Value "1"
Set-EnvDefault -Name "DROPBOX_BACKUP_DIR" -Value $DropboxBackupDir
Set-EnvDefault -Name "SANNYGOLD_BACKUP_RETENTION_LIMIT" -Value "30"
Set-EnvDefault -Name "SANNYGOLD_DROPBOX_BACKUP_RETENTION_LIMIT" -Value "30"
Set-EnvDefault -Name "PORT" -Value $DefaultPort
Set-EnvDefault -Name "FLASK_HOST" -Value $DefaultHost
Set-EnvDefault -Name "FLASK_DEBUG" -Value "0"
Set-EnvDefault -Name "SANNYGOLD_SESSION_COOKIE_SECURE" -Value "0"
Set-EnvDefault -Name "SANNYGOLD_CSRF_DISABLED" -Value "0"

$dropboxRoot = Join-Path $env:USERPROFILE "Dropbox"
Assert-NotInsideDropbox -Label "a pasta inteira do sistema" -PathToCheck $ProjectRoot -DropboxRoot $dropboxRoot
Assert-NotInsideDropbox -Label "ROTAFLOW_STORAGE_DIR" -PathToCheck $env:ROTAFLOW_STORAGE_DIR -DropboxRoot $dropboxRoot
Assert-NotInsideDropbox -Label "data/" -PathToCheck (Join-Path $env:ROTAFLOW_STORAGE_DIR "data") -DropboxRoot $dropboxRoot
Assert-NotInsideDropbox -Label "uploads/" -PathToCheck (Join-Path $env:ROTAFLOW_STORAGE_DIR "uploads") -DropboxRoot $dropboxRoot
Assert-NotInsideDropbox -Label "SANNYGOLD_SQLITE_PATH" -PathToCheck $env:SANNYGOLD_SQLITE_PATH -DropboxRoot $dropboxRoot

if (Test-Path $dropboxRoot) {
    New-Item -ItemType Directory -Force -Path $env:DROPBOX_BACKUP_DIR | Out-Null
}

if (-not (Test-Path $VenvPython)) {
    Invoke-Python -PythonCommand $PythonCommand -Arguments @("-m", "venv", $VenvDir) | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao criar ambiente virtual em .venv."
    }
}

$requirementsPath = Join-Path $ProjectRoot "requirements.txt"
$stampFile = Join-Path $VenvDir ".requirements.sha256"
$requirementsHash = (Get-FileHash -Algorithm SHA256 -Path $requirementsPath).Hash.ToLowerInvariant()
$installedHash = ""
if (Test-Path $stampFile) {
    $installedHash = (Get-Content -Path $stampFile -Raw).Trim().ToLowerInvariant()
}

if ($installedHash -ne $requirementsHash) {
    & $VenvPython -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar dependencias de requirements.txt."
    }
    Set-Content -Path $stampFile -Encoding ASCII -Value $requirementsHash
}

if ($SetupOnly -or $env:SANNYGOLD_START_WINDOWS_SETUP_ONLY -eq "1") {
    exit 0
}

& $VenvPython (Join-Path $ProjectRoot "scripts\create_local_backup.py") --trigger inicializacao_windows --if-older-hours 24
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Backup inicial nao foi concluido. O sistema continuara iniciando."
}

& $VenvPython (Join-Path $ProjectRoot "scripts\migrate_json_to_sqlite.py") --data-dir (Join-Path $ProjectRoot "data") --db $env:SANNYGOLD_SQLITE_PATH
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Migracao JSON para SQLite nao foi concluida. Verifique os logs se o problema continuar."
}

$localUrl = "http://127.0.0.1:$($env:PORT)"
$wifiIp = Get-LocalWifiIp

Write-Host "URL local: $localUrl"
if ($wifiIp) {
    Write-Host "URL para celular no Wi-Fi: http://$($wifiIp):$($env:PORT)"
}
else {
    Write-Host "URL para celular no Wi-Fi: nao foi possivel detectar IP local."
}
Write-Host "Pasta Dropbox para backups: $($env:DROPBOX_BACKUP_DIR)"
Write-Host "Pressione Ctrl+C para encerrar."

& $VenvPython -m waitress --host $env:FLASK_HOST --port $env:PORT app.main:app
