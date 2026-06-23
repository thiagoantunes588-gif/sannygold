#define AppName "SannyGold Sistema"
#define InstallerName "SannyGold Sistema - Instalador Windows"
#define AppVersion "1.0.0"
#define AppPublisher "SannyGold"
#ifndef SourceDir
#define SourceDir "..\..\dist\windows\SannyGold Sistema"
#endif
#ifndef OutputDir
#define OutputDir "..\..\dist\installers"
#endif
#define IconFile "..\..\installer\windows\assets\sannygold.ico"
#define WizardImageFile "..\..\installer\windows\assets\sannygold-wizard.bmp"
#define WizardSmallImageFile "..\..\installer\windows\assets\sannygold-small.bmp"
#define InfoBeforeFile "..\..\installer\windows\INFO-ANTES-DE-INSTALAR-WINDOWS.txt"

[Setup]
AppId={{A0F67F9B-02B4-4B76-B70C-1F40F01D3C0C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName}
AppPublisher={#AppPublisher}
AppPublisherURL=https://sannygold.com.br
AppSupportURL=https://sannygold.com.br
AppUpdatesURL=https://sannygold.com.br
DefaultDirName={localappdata}\SannyGold Sistema
DefaultGroupName=SannyGold Sistema
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=SannyGold-Sistema-Windows-Setup
#ifexist IconFile
SetupIconFile={#IconFile}
#endif
#ifexist WizardImageFile
WizardImageFile={#WizardImageFile}
WizardImageBackColor=$FDFAF1
#endif
#ifexist WizardSmallImageFile
WizardSmallImageFile={#WizardSmallImageFile}
#endif
UninstallDisplayIcon={app}\SannyGold Sistema.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile={#InfoBeforeFile}
SetupLogging=yes
CloseApplications=no

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Messages]
WelcomeLabel1={#InstallerName}
WelcomeLabel2=Instale o Sistema SannyGold para operação local com backup seguro no Dropbox.%n%nO Dropbox será usado apenas para backups e instaladores. O banco ativo do sistema ficará protegido no computador.
FinishedHeadingLabel=SannyGold Sistema instalado

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Opções de instalação:"; Flags: checkedonce

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\LEIA-ANTES-DE-INSTALAR-WINDOWS.md"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\data"
Name: "{app}\uploads"
Name: "{app}\preview"
Name: "{app}\tmp"
Name: "{app}\logs"
Name: "{app}\backups"

[Icons]
Name: "{autoprograms}\SannyGold Sistema"; Filename: "{app}\SannyGold Sistema.exe"; WorkingDir: "{app}"; IconFilename: "{app}\SannyGold Sistema.exe"
Name: "{autodesktop}\SannyGold Sistema"; Filename: "{app}\SannyGold Sistema.exe"; WorkingDir: "{app}"; IconFilename: "{app}\SannyGold Sistema.exe"; Tasks: desktopicon
Name: "{autoprograms}\Diagnóstico SannyGold"; Filename: "{app}\SannyGold Sistema.exe"; Parameters: "--diagnostico"; WorkingDir: "{app}"; IconFilename: "{app}\SannyGold Sistema.exe"
Name: "{autoprograms}\Pasta de Backups SannyGold"; Filename: "{app}\backups"; WorkingDir: "{app}"

[Run]
Filename: "{app}\SannyGold Sistema.exe"; Description: "Abrir SannyGold Sistema após instalar"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\logs\launcher.lock"

[Code]
procedure CurPageChanged(CurPageID: Integer);
var
  DropboxPath: String;
begin
  if CurPageID = wpFinished then
  begin
    DropboxPath := ExpandConstant('{userprofile}\Dropbox\Sistema SannyGold\Backups');
    WizardForm.FinishedLabel.Caption :=
      'Instalação concluída.' + #13#10 + #13#10 +
      'Local de instalação: ' + ExpandConstant('{app}') + #13#10 +
      'Local dos dados: ' + ExpandConstant('{app}\data') + #13#10 +
      'Local dos backups locais: ' + ExpandConstant('{app}\backups') + #13#10 +
      'Local esperado do Dropbox: ' + DropboxPath + #13#10 + #13#10 +
      'Não mova a pasta instalada para dentro do Dropbox. O Dropbox deve receber apenas instaladores e backups .zip.';
  end;
end;
