param(
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$AppName = "SannyGold Sistema"
$SetupFileName = "SannyGold-Sistema-Windows-Setup.exe"
$PortableFileName = "SannyGold-Sistema-Windows-Portable.zip"
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "build-windows.log"
$DropboxRoot = Join-Path $env:USERPROFILE "Dropbox"
$DropboxSystemRoot = Join-Path $DropboxRoot "Sistema SannyGold"
$DropboxInstallersDir = Join-Path $DropboxSystemRoot "Instaladores"
$DropboxWindowsRoot = Join-Path $DropboxInstallersDir "Windows"
$DropboxWindowsDir = Join-Path $DropboxWindowsRoot "Instalador"
$FinalSetup = Join-Path $DropboxWindowsDir $SetupFileName
$FinalPortable = Join-Path $DropboxWindowsDir $PortableFileName
$FinalReadme = Join-Path $DropboxWindowsRoot "LEIA-ME.md"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-BuildLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Encoding UTF8 -Value "[$timestamp] $Message"
}

function Assert-WindowsBuildHost {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw "Este comando unico precisa ser executado no Windows 10/11 para gerar pacotes Windows reais."
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

function Invoke-BuildStep {
    param(
        [string]$Label,
        [string]$ScriptPath,
        [string[]]$Arguments = @()
    )
    Write-Host ""
    Write-Host "== $Label =="
    Write-BuildLog "Iniciando etapa: $Label"
    & $ScriptPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha na etapa: $Label"
    }
    Write-BuildLog "Etapa concluida: $Label"
}

function Sync-WindowsDocumentation {
    New-Item -ItemType Directory -Force -Path `
        $DropboxWindowsDir, `
        (Join-Path $DropboxWindowsRoot "Atualizações"), `
        (Join-Path $DropboxInstallersDir "Mac\Instalador"), `
        (Join-Path $DropboxInstallersDir "Mac\Atualizações"), `
        (Join-Path $DropboxInstallersDir "Celular\Android"), `
        (Join-Path $DropboxInstallersDir "Celular\iPhone-iOS"), `
        (Join-Path $DropboxInstallersDir "Celular\Atalho-Web"), `
        (Join-Path $DropboxInstallersDir "Arquivados"), `
        (Join-Path $DropboxInstallersDir "_Revisao_Antes_de_Excluir") | Out-Null
    Copy-Item -Force (Join-Path $ProjectRoot "installer\LEIA-ME.md") (Join-Path $DropboxInstallersDir "LEIA-ME.md")
    Copy-Item -Force (Join-Path $ProjectRoot "installer\windows\LEIA-ME.md") $FinalReadme
    Copy-Item -Force (Join-Path $ProjectRoot "installer\mac\LEIA-ME.md") (Join-Path $DropboxInstallersDir "Mac\LEIA-ME.md")
    Copy-Item -Force (Join-Path $ProjectRoot "installer\celular\LEIA-ME.md") (Join-Path $DropboxInstallersDir "Celular\LEIA-ME.md")
}

function Assert-FinalWindowsFolder {
    param([bool]$InnoAvailable)

    Sync-WindowsDocumentation

    $portableExists = Test-Path $FinalPortable
    $setupExists = Test-Path $FinalSetup

    if (-not (Test-Path $FinalReadme)) {
        throw "Arquivo obrigatorio ausente: $FinalReadme"
    }
    if (-not $portableExists -and -not $setupExists) {
        throw "ERRO: nenhum pacote Windows foi gerado."
    }
    if (-not $portableExists) {
        throw "Arquivo obrigatorio ausente: $FinalPortable"
    }
    if ($InnoAvailable -and -not $setupExists) {
        throw "Inno Setup foi encontrado, mas o instalador visual nao foi gerado: $FinalSetup"
    }
    if ($setupExists -and ((Get-Item $FinalSetup).Length -le 10MB)) {
        throw "Instalador visual parece incompleto: $FinalSetup tem $(Get-ReadableFileSize -Path $FinalSetup), esperado maior que 10 MB."
    }

    Write-Host ""
    Write-Host "Validacao final da pasta Windows:"
    Write-Host "README: $FinalReadme"
    Write-Host "Portable.zip: $FinalPortable ($(Get-ReadableFileSize -Path $FinalPortable))"
    if ($setupExists) {
        Write-Host "Instalador visual: $FinalSetup ($(Get-ReadableFileSize -Path $FinalSetup))"
    }
    elseif (-not $InnoAvailable) {
        Write-Host "Versão portátil criada. Instalador visual não criado porque Inno Setup não foi encontrado."
    }
}

try {
    Assert-WindowsBuildHost
    Write-BuildLog "Build completo Windows iniciado"

    $buildAppArgs = @()
    if ($SkipDependencyInstall) {
        $buildAppArgs += "-SkipDependencyInstall"
    }

    Invoke-BuildStep -Label "1. App Windows" -ScriptPath (Join-Path $ProjectRoot "scripts\build_windows_app.ps1") -Arguments $buildAppArgs
    Invoke-BuildStep -Label "2. Zip portatil" -ScriptPath (Join-Path $ProjectRoot "scripts\package_windows_portable.ps1") -Arguments @("-SkipAppBuild")

    $innoCompiler = Find-InnoCompiler
    if ($innoCompiler) {
        Write-Host ""
        Write-Host "Inno Setup encontrado: $innoCompiler"
        Invoke-BuildStep -Label "3. Instalador visual Inno Setup" -ScriptPath (Join-Path $ProjectRoot "scripts\build_windows_installer.ps1") -Arguments @("-SkipAppBuild")
    }
    else {
        Write-Host ""
        Write-Host "Versão portátil criada. Instalador visual não criado porque Inno Setup não foi encontrado."
        Write-BuildLog "Inno Setup nao encontrado. Instalador visual ignorado."
    }

    Write-Host ""
    Write-Host "== 4. Validacao final Dropbox Windows =="
    Assert-FinalWindowsFolder -InnoAvailable ([bool]$innoCompiler)

    Write-BuildLog "Build completo Windows concluido"
    Write-Host ""
    Write-Host "BUILD WINDOWS CONCLUIDO"
}
catch {
    Write-BuildLog "Erro no build completo Windows: $($_.Exception.Message)"
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Veja o log em: $LogFile"
    exit 1
}
