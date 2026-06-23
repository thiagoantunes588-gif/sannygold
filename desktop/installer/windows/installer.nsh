!macro preInit
  SetRegView 64
  WriteRegExpandStr HKLM "${INSTALL_REGISTRY_KEY}" InstallLocation "$PROGRAMFILES64\SannySystem"
  WriteRegExpandStr HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation "$PROGRAMFILES64\SannySystem"
!macroend

!macro customInstall
  SetShellVarContext all
  CreateDirectory "$APPDATA\SannySystem"
  CreateDirectory "$APPDATA\SannySystem\logs"
  CreateDirectory "$APPDATA\SannySystem\config"
  CreateDirectory "$APPDATA\SannySystem\recovery"

  IfFileExists "$PROFILE\Dropbox\*.*" DropboxFound DropboxDone
  DropboxFound:
    CreateDirectory "$PROFILE\Dropbox\SannySystemData"
    CreateDirectory "$PROFILE\Dropbox\SannySystemData\logs"
    CreateDirectory "$PROFILE\Dropbox\SannySystemData\backups"
    CreateDirectory "$PROFILE\Dropbox\SannySystemData\temp"
    CreateDirectory "$PROFILE\Dropbox\SannySystemData\exports"
    CreateDirectory "$PROFILE\Dropbox\SannySystemData\uploads"
    CreateDirectory "$PROFILE\Dropbox\SannySystemData\config"
  DropboxDone:

  FileOpen $0 "$APPDATA\SannySystem\logs\install.log" a
  FileWrite $0 "SannySystem instalado em $INSTDIR$\r$\n"
  FileWrite $0 "AppData: $APPDATA\SannySystem$\r$\n"
  FileWrite $0 "Dropbox padrao verificado em $PROFILE\Dropbox$\r$\n"
  FileClose $0
!macroend

!macro customUnInstall
  SetShellVarContext all
  CreateDirectory "$APPDATA\SannySystem\logs"
  FileOpen $0 "$APPDATA\SannySystem\logs\uninstall.log" a
  FileWrite $0 "SannySystem removido de $INSTDIR$\r$\n"
  FileClose $0
!macroend
