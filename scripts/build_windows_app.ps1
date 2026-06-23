param(
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
$DistRoot = Join-Path $ProjectRoot "dist\windows"
$BuildRoot = Join-Path $ProjectRoot "build\windows"
$StageRoot = Join-Path $ProjectRoot "build\windows-stage"
$AppName = "SannyGold Sistema"
$AppDistDir = Join-Path $DistRoot $AppName
$AppExe = Join-Path $AppDistDir "SannyGold Sistema.exe"
$RelativeLogFile = "logs\build-windows.log"
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $ProjectRoot $RelativeLogFile
$IconPath = Join-Path $ProjectRoot "installer\windows\assets\sannygold.ico"
$WizardImagePath = Join-Path $ProjectRoot "installer\windows\assets\sannygold-wizard.bmp"
$WizardSmallImagePath = Join-Path $ProjectRoot "installer\windows\assets\sannygold-small.bmp"
$LogoPath = Join-Path $ProjectRoot "app\static\sannygold-logo.jpg"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-BuildLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Encoding UTF8 -Value "[$timestamp] $Message"
}

function Assert-WindowsBuildHost {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw "Este build precisa ser executado no Windows 10/11. O PyInstaller nao gera um executavel Windows real quando rodado no macOS ou Linux."
    }
}

function Get-SystemPythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    throw "Python 3 nao encontrado. Instale Python para Windows e marque a opcao 'Add python.exe to PATH'."
}

function Invoke-SystemPython {
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

function New-SannyGoldIcon {
    if (Test-Path $IconPath) {
        return
    }
    if (-not (Test-Path $LogoPath)) {
        Write-BuildLog "Logo nao encontrado para gerar icone: $LogoPath"
        return
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $IconPath) | Out-Null
    Add-Type -AssemblyName System.Drawing
    $bitmap = [System.Drawing.Bitmap]::FromFile($LogoPath)
    try {
        $resized = New-Object System.Drawing.Bitmap 256, 256
        $graphics = [System.Drawing.Graphics]::FromImage($resized)
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.DrawImage($bitmap, 0, 0, 256, 256)
        $handle = $resized.GetHicon()
        $icon = [System.Drawing.Icon]::FromHandle($handle)
        $stream = [System.IO.File]::Open($IconPath, [System.IO.FileMode]::Create)
        try {
            $icon.Save($stream)
        }
        finally {
            $stream.Close()
            $icon.Dispose()
            $graphics.Dispose()
            $resized.Dispose()
        }
    }
    finally {
        $bitmap.Dispose()
    }
}

function New-SannyGoldInstallerImages {
    if ((Test-Path $WizardImagePath) -and (Test-Path $WizardSmallImagePath)) {
        return
    }
    if (-not (Test-Path $LogoPath)) {
        Write-BuildLog "Logo nao encontrado para gerar imagens do instalador: $LogoPath"
        return
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $WizardImagePath) | Out-Null
    Add-Type -AssemblyName System.Drawing
    $logo = [System.Drawing.Bitmap]::FromFile($LogoPath)
    try {
        if (-not (Test-Path $WizardImagePath)) {
            $bitmap = New-Object System.Drawing.Bitmap -ArgumentList 164, 314
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            $lightBrush = New-Object System.Drawing.SolidBrush -ArgumentList ([System.Drawing.Color]::FromArgb(253, 250, 241))
            $goldBrush = New-Object System.Drawing.SolidBrush -ArgumentList ([System.Drawing.Color]::FromArgb(179, 137, 54))
            $darkBrush = New-Object System.Drawing.SolidBrush -ArgumentList ([System.Drawing.Color]::FromArgb(42, 39, 31))
            $mutedBrush = New-Object System.Drawing.SolidBrush -ArgumentList ([System.Drawing.Color]::FromArgb(97, 88, 65))
            $titleFont = New-Object System.Drawing.Font -ArgumentList "Segoe UI", 14, ([System.Drawing.FontStyle]::Bold)
            $bodyFont = New-Object System.Drawing.Font -ArgumentList "Segoe UI", 8.5, ([System.Drawing.FontStyle]::Regular)
            $format = New-Object System.Drawing.StringFormat
            try {
                $graphics.Clear([System.Drawing.Color]::White)
                $graphics.FillRectangle($lightBrush, 0, 0, 164, 314)
                $graphics.FillRectangle($goldBrush, 0, 0, 8, 314)
                $ratio = [Math]::Min(118 / $logo.Width, 92 / $logo.Height)
                $drawWidth = [int]($logo.Width * $ratio)
                $drawHeight = [int]($logo.Height * $ratio)
                $drawX = [int]((164 - $drawWidth) / 2)
                $graphics.DrawImage($logo, $drawX, 34, $drawWidth, $drawHeight)
                $format.Alignment = [System.Drawing.StringAlignment]::Center
                $graphics.DrawString("SannyGold", $titleFont, $darkBrush, (New-Object System.Drawing.RectangleF -ArgumentList 14, 154, 136, 34), $format)
                $graphics.DrawString("Sistema local`nBackup seguro`nno Dropbox", $bodyFont, $mutedBrush, (New-Object System.Drawing.RectangleF -ArgumentList 18, 196, 128, 62), $format)
                $graphics.FillRectangle($goldBrush, 28, 282, 108, 3)
                $bitmap.Save($WizardImagePath, [System.Drawing.Imaging.ImageFormat]::Bmp)
            }
            finally {
                $format.Dispose()
                $bodyFont.Dispose()
                $titleFont.Dispose()
                $mutedBrush.Dispose()
                $darkBrush.Dispose()
                $goldBrush.Dispose()
                $lightBrush.Dispose()
                $graphics.Dispose()
                $bitmap.Dispose()
            }
        }

        if (-not (Test-Path $WizardSmallImagePath)) {
            $bitmap = New-Object System.Drawing.Bitmap -ArgumentList 55, 55
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            $backgroundBrush = New-Object System.Drawing.SolidBrush -ArgumentList ([System.Drawing.Color]::FromArgb(253, 250, 241))
            $borderPen = New-Object System.Drawing.Pen -ArgumentList ([System.Drawing.Color]::FromArgb(179, 137, 54)), 2
            try {
                $graphics.Clear([System.Drawing.Color]::White)
                $graphics.FillRectangle($backgroundBrush, 0, 0, 55, 55)
                $graphics.DrawRectangle($borderPen, 1, 1, 52, 52)
                $ratio = [Math]::Min(39 / $logo.Width, 39 / $logo.Height)
                $drawWidth = [int]($logo.Width * $ratio)
                $drawHeight = [int]($logo.Height * $ratio)
                $drawX = [int]((55 - $drawWidth) / 2)
                $drawY = [int]((55 - $drawHeight) / 2)
                $graphics.DrawImage($logo, $drawX, $drawY, $drawWidth, $drawHeight)
                $bitmap.Save($WizardSmallImagePath, [System.Drawing.Imaging.ImageFormat]::Bmp)
            }
            finally {
                $borderPen.Dispose()
                $backgroundBrush.Dispose()
                $graphics.Dispose()
                $bitmap.Dispose()
            }
        }
    }
    finally {
        $logo.Dispose()
    }
}

function Copy-CleanTree {
    param(
        [string]$Source,
        [string]$Destination
    )
    robocopy $Source $Destination /E /XD "__pycache__" ".pytest_cache" ".mypy_cache" "data" "uploads" "preview" "backups" "logs" "tmp" ".venv" /XF ".env" ".env.local" "*.pyc" "*.pyo" | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Falha ao copiar arquivos de $Source para $Destination."
    }
}

try {
    Assert-WindowsBuildHost
    Write-BuildLog "Build Windows iniciado em $ProjectRoot"
    $PythonCommand = Get-SystemPythonCommand

    if (-not (Test-Path $VenvPython)) {
        Write-BuildLog "Criando .venv"
        Invoke-SystemPython -PythonCommand $PythonCommand -Arguments @("-m", "venv", $VenvDir)
    }

    if (-not $SkipDependencyInstall) {
        Write-BuildLog "Instalando requirements.txt"
        & $VenvPython -m pip install --upgrade pip
        & $VenvPython -m pip install -r $RequirementsPath
        & $VenvPython -m pip install pyinstaller
    }

    New-SannyGoldIcon
    New-SannyGoldInstallerImages

    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $AppDistDir, $BuildRoot, $StageRoot
    New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null
    Copy-CleanTree -Source (Join-Path $ProjectRoot "app") -Destination (Join-Path $StageRoot "app")
    Copy-CleanTree -Source (Join-Path $ProjectRoot "scripts") -Destination (Join-Path $StageRoot "scripts")
    Copy-Item -Force $RequirementsPath (Join-Path $StageRoot "requirements.txt")
    Copy-Item -Force (Join-Path $ProjectRoot ".env.example") (Join-Path $StageRoot ".env.example") -ErrorAction SilentlyContinue
    Copy-Item -Force $IconPath (Join-Path $StageRoot "sannygold.ico") -ErrorAction SilentlyContinue

    $launcher = Join-Path $StageRoot "scripts\sannygold_launcher.py"
    $pyInstallerArgs = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name", $AppName,
        "--contents-directory", ".",
        "--distpath", $DistRoot,
        "--workpath", $BuildRoot,
        "--specpath", $BuildRoot,
        "--add-data", "$($StageRoot)\app;app",
        "--add-data", "$($StageRoot)\scripts;scripts",
        "--add-data", "$($StageRoot)\requirements.txt;."
    )
    if (Test-Path $IconPath) {
        $pyInstallerArgs += @("--icon", $IconPath)
    }
    $pyInstallerArgs += $launcher

    Write-BuildLog "Executando PyInstaller"
    & $VenvPython @pyInstallerArgs *>> $LogFile
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller falhou. Veja o log em $LogFile."
    }

    foreach ($folder in @("data", "uploads", "preview", "tmp", "logs", "backups")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $AppDistDir $folder) | Out-Null
    }
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $AppDistDir ".env.local")

    if (-not (Test-Path $AppExe)) {
        throw "PyInstaller terminou, mas o executavel esperado nao existe: $AppExe"
    }

    Write-BuildLog "Build Windows concluido em $AppExe"
    Write-Host "Build gerado em: $AppDistDir"
    Write-Host "Executavel gerado em: $AppExe"
}
catch {
    Write-BuildLog "Erro: $($_.Exception.Message)"
    Write-Host "Falha ao gerar o aplicativo Windows." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Veja o log em: $LogFile"
    exit 1
}
