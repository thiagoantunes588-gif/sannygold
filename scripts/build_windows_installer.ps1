param(
    [switch]$SkipAppBuild
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$AppName = "SannyGold Sistema"
$SetupFileName = "SannyGold-Sistema-Windows-Setup.exe"
$PortableFileName = "SannyGold-Sistema-Windows-Portable.zip"
$AppDistDir = Join-Path $ProjectRoot "dist\windows\$AppName"
$AppExe = Join-Path $AppDistDir "$AppName.exe"
$InstallerOutputDir = Join-Path $ProjectRoot "dist\installers"
$InstallerOutputPath = Join-Path $InstallerOutputDir $SetupFileName
$PortableBuildPath = Join-Path $InstallerOutputDir $PortableFileName
$InnoScript = Join-Path $ProjectRoot "installer\windows\sannygold-windows.iss"
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "build-windows.log"
$DropboxRoot = Join-Path $env:USERPROFILE "Dropbox"
$DropboxSystemRoot = Join-Path $DropboxRoot "Sistema SannyGold"
$DropboxBackupsDir = Join-Path $DropboxSystemRoot "Backups"
$DropboxInstallersDir = Join-Path $DropboxSystemRoot "Instaladores"
$DropboxWindowsRoot = Join-Path $DropboxInstallersDir "Windows"
$DropboxWindowsDir = Join-Path $DropboxWindowsRoot "Instalador"
$DropboxMacDir = Join-Path $DropboxInstallersDir "Mac"
$DropboxMobileDir = Join-Path $DropboxInstallersDir "Celular"
$DropboxArchivedDir = Join-Path $DropboxInstallersDir "Arquivados"
$DropboxReviewDir = Join-Path $DropboxInstallersDir "_Revisao_Antes_de_Excluir"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-BuildLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Encoding UTF8 -Value "[$timestamp] $Message"
}

function Assert-WindowsBuildHost {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw "Este instalador precisa ser gerado no Windows 10/11. O Inno Setup e o PyInstaller nao produzem o SannyGold-Sistema-Windows-Setup.exe real a partir do macOS ou Linux."
    }
}

function Get-ReadableFileSize {
    param([string]$Path)
    $bytes = (Get-Item $Path).Length
    if ($bytes -ge 1GB) {
        return "{0:N2} GB" -f ($bytes / 1GB)
    }
    if ($bytes -ge 1MB) {
        return "{0:N2} MB" -f ($bytes / 1MB)
    }
    if ($bytes -ge 1KB) {
        return "{0:N2} KB" -f ($bytes / 1KB)
    }
    return "$bytes bytes"
}

function Find-InnoCompiler {
    $fromPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($fromPath) {
        return $fromPath.Source
    }
    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
        "C:\Program Files\Inno Setup 7\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }
    return $null
}

function Install-InnoSetupWithWinget {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "Instale o Inno Setup para gerar o instalador .exe visual."
        Write-BuildLog "winget nao encontrado; Inno Setup nao pode ser instalado automaticamente."
        return $false
    }

    $answer = Read-Host "Inno Setup não encontrado. Deseja instalar agora via winget? S/N"
    if ($answer -notmatch "^[sS]$") {
        Write-BuildLog "Usuario optou por nao instalar Inno Setup via winget."
        return $false
    }

    Write-BuildLog "Instalando Inno Setup via winget"
    & winget install --id JRSoftware.InnoSetup -e -s winget
    if ($LASTEXITCODE -ne 0) {
        Write-BuildLog "winget falhou ao instalar Inno Setup. Codigo: $LASTEXITCODE"
        return $false
    }
    return $true
}

function Resolve-InnoCompiler {
    $iscc = Find-InnoCompiler
    if ($iscc) {
        return $iscc
    }

    [void](Install-InnoSetupWithWinget)
    return Find-InnoCompiler
}

function Build-PortableFallback {
    & (Join-Path $ProjectRoot "scripts\package_windows_portable.ps1") -SkipAppBuild
    if ($LASTEXITCODE -ne 0) {
        throw "Geracao da versao portatil falhou. A pasta Windows ficaria sem pacote instalavel."
    }

    $finalPortable = Join-Path $DropboxWindowsDir $PortableFileName
    if (-not (Test-Path $finalPortable)) {
        throw "Versao portatil esperada nao foi gerada em: $finalPortable"
    }
    Write-BuildLog "Instalador visual nao criado; versao portatil gerada em $finalPortable"
    Write-Host "Instalador visual não foi criado, mas a versão portátil foi gerada."
    Write-Host "Versao portatil: $finalPortable"
    Write-Host "Tamanho do zip portatil: $(Get-ReadableFileSize -Path $finalPortable)"
}

function Assert-MinimumInstallerSize {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "Instalador Windows final nao existe fisicamente em: $Path"
    }
    $size = (Get-Item $Path).Length
    if ($size -le 10MB) {
        throw "Instalador Windows final parece incompleto: $Path tem $(Get-ReadableFileSize -Path $Path), esperado maior que 10 MB."
    }
}

function Copy-InstallerReadmes {
    param([string]$InstallersDir)
    New-Item -ItemType Directory -Force -Path $InstallersDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallersDir "Mac\Instalador") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallersDir "Mac\Atualizações") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallersDir "Windows\Instalador") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallersDir "Windows\Atualizações") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallersDir "Celular\Android") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallersDir "Celular\iPhone-iOS") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallersDir "Celular\Atalho-Web") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallersDir "Arquivados") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallersDir "_Revisao_Antes_de_Excluir") | Out-Null

    Copy-Item -Force (Join-Path $ProjectRoot "installer\LEIA-ME.md") (Join-Path $InstallersDir "LEIA-ME.md")
    Copy-Item -Force (Join-Path $ProjectRoot "installer\mac\LEIA-ME.md") (Join-Path $InstallersDir "Mac\LEIA-ME.md")
    Copy-Item -Force (Join-Path $ProjectRoot "installer\windows\LEIA-ME.md") (Join-Path $InstallersDir "Windows\LEIA-ME.md")
    Copy-Item -Force (Join-Path $ProjectRoot "installer\celular\LEIA-ME.md") (Join-Path $InstallersDir "Celular\LEIA-ME.md")
}

function Move-LegacyInstallerItems {
    param([string]$InstallersDir)
    $review = Join-Path $InstallersDir "_Revisao_Antes_de_Excluir"
    New-Item -ItemType Directory -Force -Path $review | Out-Null
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

    function Move-ToInstaller {
        param([string]$SourcePath, [string]$DestinationPath)
        if (-not (Test-Path $SourcePath)) {
            return
        }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DestinationPath) | Out-Null
        if (Test-Path $DestinationPath) {
            Move-Item -Force $DestinationPath (Join-Path $review "$timestamp-$(Split-Path -Leaf $DestinationPath)")
        }
        Move-Item -Force $SourcePath $DestinationPath
    }

    function Move-ToReview {
        param([string]$SourcePath)
        if (Test-Path $SourcePath) {
            Move-Item -Force $SourcePath (Join-Path $review "$timestamp-$(Split-Path -Leaf $SourcePath)")
        }
    }

    Move-ToInstaller -SourcePath (Join-Path $InstallersDir "SannyGold Sistema.app") -DestinationPath (Join-Path $InstallersDir "Mac\Instalador\SannyGold Sistema.app")
    Move-ToInstaller -SourcePath (Join-Path $InstallersDir "SannyGold-Sistema-Mac.zip") -DestinationPath (Join-Path $InstallersDir "Mac\Instalador\SannyGold-Sistema-Mac.zip")
    Move-ToInstaller -SourcePath (Join-Path $InstallersDir "Mac\SannyGold Sistema.app") -DestinationPath (Join-Path $InstallersDir "Mac\Instalador\SannyGold Sistema.app")
    Move-ToInstaller -SourcePath (Join-Path $InstallersDir "Mac\SannyGold-Sistema-Mac.zip") -DestinationPath (Join-Path $InstallersDir "Mac\Instalador\SannyGold-Sistema-Mac.zip")

    Move-ToInstaller -SourcePath (Join-Path $InstallersDir "SannyGold-Sistema-Windows-Setup.exe") -DestinationPath (Join-Path $InstallersDir "Windows\Instalador\SannyGold-Sistema-Windows-Setup.exe")
    Move-ToInstaller -SourcePath (Join-Path $InstallersDir "SannyGold-Sistema-Windows-Portable.zip") -DestinationPath (Join-Path $InstallersDir "Windows\Instalador\SannyGold-Sistema-Windows-Portable.zip")
    Move-ToInstaller -SourcePath (Join-Path $InstallersDir "Windows\SannyGold-Sistema-Windows-Setup.exe") -DestinationPath (Join-Path $InstallersDir "Windows\Instalador\SannyGold-Sistema-Windows-Setup.exe")
    Move-ToInstaller -SourcePath (Join-Path $InstallersDir "Windows\SannyGold-Sistema-Windows-Portable.zip") -DestinationPath (Join-Path $InstallersDir "Windows\Instalador\SannyGold-Sistema-Windows-Portable.zip")

    $legacyReadmes = @(
        "LEIA-ANTES-DE-INSTALAR.md",
        "LEIA-MAC.md",
        "LEIA-WINDOWS.md",
        "LEIA-ANTES-DE-INSTALAR-WINDOWS.md",
        "Mac\LEIA-MAC.md",
        "Windows\LEIA-WINDOWS.md",
        "Windows\LEIA-ANTES-DE-INSTALAR-WINDOWS.md"
    )
    foreach ($name in $legacyReadmes) {
        Move-ToReview -SourcePath (Join-Path $InstallersDir $name)
    }
    Get-ChildItem -Path $InstallersDir -Filter "SannyGold-Sistema-Instalacao-*.zip" -ErrorAction SilentlyContinue |
        ForEach-Object { Move-Item -Force $_.FullName (Join-Path $review "$timestamp-$($_.Name)") }
}

try {
    Assert-WindowsBuildHost
    Write-BuildLog "Build do instalador Windows iniciado"

    if (-not (Test-Path $AppExe)) {
        if ($SkipAppBuild) {
            throw "Executavel nao encontrado: $AppExe. Rode scripts\build_windows_app.ps1 antes de usar -SkipAppBuild."
        }
        Write-BuildLog "Executavel Windows nao encontrado. Rodando build_windows_app.ps1."
        & (Join-Path $ProjectRoot "scripts\build_windows_app.ps1")
        if ($LASTEXITCODE -ne 0) {
            throw "Build do aplicativo Windows falhou."
        }
    }

    if (-not (Test-Path $AppExe)) {
        throw "Executavel nao encontrado: $AppExe"
    }

    $iscc = Resolve-InnoCompiler
    if (-not $iscc) {
        Build-PortableFallback
        exit 0
    }

    New-Item -ItemType Directory -Force -Path $InstallerOutputDir | Out-Null
    Remove-Item -Force -ErrorAction SilentlyContinue $InstallerOutputPath

    Write-BuildLog "Compilando Inno Setup com $iscc"
    & $iscc "/DSourceDir=$AppDistDir" "/DOutputDir=$InstallerOutputDir" $InnoScript *>> $LogFile
    if ($LASTEXITCODE -ne 0) {
        throw "Compilacao do Inno Setup falhou. Veja o log em $LogFile."
    }

    $compiledSetup = $InstallerOutputPath
    if (-not (Test-Path $compiledSetup)) {
        throw "Instalador esperado nao foi gerado: $compiledSetup"
    }
    Assert-MinimumInstallerSize -Path $compiledSetup

    if (-not (Test-Path $DropboxRoot)) {
        throw "Dropbox nao encontrado em: $DropboxRoot. O instalador final precisa ser copiado para Dropbox\Sistema SannyGold\Instaladores\Windows\Instalador."
    }

    New-Item -ItemType Directory -Force -Path `
        $DropboxBackupsDir, `
        $DropboxWindowsDir, `
        (Join-Path $DropboxWindowsRoot "Atualizações"), `
        (Join-Path $DropboxMacDir "Instalador"), `
        (Join-Path $DropboxMacDir "Atualizações"), `
        (Join-Path $DropboxMobileDir "Android"), `
        (Join-Path $DropboxMobileDir "iPhone-iOS"), `
        (Join-Path $DropboxMobileDir "Atalho-Web"), `
        $DropboxArchivedDir, `
        $DropboxReviewDir | Out-Null
    Move-LegacyInstallerItems -InstallersDir $DropboxInstallersDir
    Copy-InstallerReadmes -InstallersDir $DropboxInstallersDir
    $finalSetup = Join-Path $DropboxWindowsDir $SetupFileName

    Copy-Item -Force $compiledSetup $finalSetup

    Assert-MinimumInstallerSize -Path $finalSetup

    Write-BuildLog "Instalador Windows gerado em $finalSetup"
    Write-Host "Instalador Windows gerado em: $finalSetup"
    Write-Host "Tamanho do instalador: $(Get-ReadableFileSize -Path $finalSetup)"
    Write-Host "Copia local em: $InstallerOutputPath"
    Write-Host "Status final: INSTALADOR WINDOWS GERADO COM SUCESSO" -ForegroundColor Green
}
catch {
    Write-BuildLog "Erro: $($_.Exception.Message)"
    Write-Host "Falha ao gerar o instalador Windows." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Veja o log em: $LogFile"
    exit 1
}
