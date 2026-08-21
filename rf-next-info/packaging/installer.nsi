Unicode True
!ifdef DEV_SMOKE
RequestExecutionLevel user
!else
RequestExecutionLevel admin
!endif
!ifdef STAGING_PROFILE
!define APP_DISPLAY_NAME "RF QOL 2.0 Homologacao"
!define APP_REGKEY "Software\Karvalho\RFQOLStaging"
!define APP_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL Staging"
!define APP_SHORTCUT_NAME "RF QOL 2.0 Homologacao"
!else
!ifdef BETA_PROFILE
!define APP_DISPLAY_NAME "RF QOL 2.0 Beta"
!define APP_REGKEY "Software\Karvalho\RFQOLBeta"
!define APP_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL Beta"
!define APP_SHORTCUT_NAME "RF QOL 2.0 Beta"
!else
!define APP_DISPLAY_NAME "RF QOL"
!define APP_REGKEY "Software\Karvalho\RFQOL"
!define APP_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL"
!define APP_SHORTCUT_NAME "RF QOL"
!endif
!endif
Name "${APP_DISPLAY_NAME}"
!ifndef APP_VERSION
!define APP_VERSION "1.0.8"
!endif
!ifndef APP_FILE_VERSION
!define APP_FILE_VERSION "1.0.8.0"
!endif
!ifndef APP_SOURCE
!define APP_SOURCE "..\dist\RF QOL"
!endif
!ifndef APP_OUTFILE
!define APP_OUTFILE "..\dist\RF QOL Setup ${APP_VERSION}.exe"
!endif
!ifndef APP_INSTALLDIR
!ifdef STAGING_PROFILE
!define APP_INSTALLDIR "$PROGRAMFILES64\Karvalho\RF QOL Staging"
!else
!ifdef BETA_PROFILE
!define APP_INSTALLDIR "$PROGRAMFILES64\Karvalho\RF QOL Beta"
!else
!define APP_INSTALLDIR "$PROGRAMFILES64\Karvalho\RF QOL"
!endif
!endif
!endif
OutFile "${APP_OUTFILE}"
InstallDir "${APP_INSTALLDIR}"
!ifndef DEV_SMOKE
InstallDirRegKey HKLM "${APP_REGKEY}" "InstallDir"
!endif
SetCompressor /SOLID lzma
CRCCheck on

VIProductVersion "${APP_FILE_VERSION}"
VIAddVersionKey /LANG=1046 "ProductName" "${APP_DISPLAY_NAME}"
VIAddVersionKey /LANG=1046 "CompanyName" "Karvalho"
VIAddVersionKey /LANG=1046 "FileDescription" "Instalador do RF QOL"
VIAddVersionKey /LANG=1046 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1046 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1046 "LegalCopyright" "Karvalho"

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_LICENSEPAGE_CHECKBOX_TEXT "Li e aceito os Termos de Uso"
!insertmacro MUI_PAGE_LICENSE "..\docs\TERMOS-DE-USO-RF-QOL-1.0.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Function EnsureAppClosed
  IfFileExists "$INSTDIR\RF QOL.exe" 0 done
retry:
  ClearErrors
  FileOpen $0 "$INSTDIR\RF QOL.exe" a
  IfErrors running
  FileClose $0
  Goto done
running:
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
    "Feche o RF QOL antes de continuar.$\r$\n$\r$\nSe houver captura ativa, cancele a instalação, pare a captura e aguarde a leitura. Depois tente novamente." \
    IDRETRY retry
  Abort
done:
FunctionEnd

Section "RF QOL" SEC_APP
  Call EnsureAppClosed
  Sleep 1500
  RMDir /r "$INSTDIR\_internal"
  SetOutPath "$INSTDIR"
  File /r "${APP_SOURCE}\*.*"
!ifdef DEV_SMOKE
  SetShellVarContext current
!else
  SetShellVarContext all
!endif
  CreateDirectory "$INSTDIR\data"
  CreateDirectory "$INSTDIR\database"
  CreateDirectory "$INSTDIR\logs"
  CreateDirectory "$INSTDIR\cache"
!ifndef DEV_SMOKE
  CreateDirectory "$APPDATA\Karvalho\RF QOL"
  CreateDirectory "$APPDATA\Karvalho\RF QOL\updates"
!endif
  CreateDirectory "$INSTDIR\Capturas"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  ClearErrors
  StrCpy $0 -1
  Delete "$INSTDIR\logs\self-test.ok"
  ExecWait '$\"$INSTDIR\RF QOL.exe$\" --self-test' $0
  IfErrors self_test_exec_failed
  StrCmp $0 0 self_test_log self_test_exec_failed
self_test_exec_failed:
  StrCpy $0 -1
self_test_log:
  FileOpen $1 "$INSTDIR\logs\install.log" a
  FileWrite $1 "version=${APP_VERSION} self_test=$0$\r$\n"
  FileClose $1
  SetShellVarContext current
  StrCmp $0 0 self_test_ok
  MessageBox MB_OK|MB_ICONSTOP \
    "O teste do programa instalado falhou (código $0). Consulte o arquivo install.log e não abra o RF QOL."
  Abort
self_test_ok:
!ifndef DEV_SMOKE
  WriteRegStr HKLM "${APP_REGKEY}" "InstallDir" "$INSTDIR"
!endif
!ifndef DEV_SMOKE
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayName" "${APP_DISPLAY_NAME}"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "Publisher" "Karvalho"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "URLInfoAbout" "https://karvalho.dev.br/"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "HelpLink" "https://discord.gg/D3hhdMgkj"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\RF QOL.exe"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKLM "${APP_UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${APP_UNINSTALL_KEY}" "NoRepair" 1
  CreateDirectory "$SMPROGRAMS\Karvalho"
  CreateShortcut "$SMPROGRAMS\Karvalho\${APP_SHORTCUT_NAME}.lnk" "$INSTDIR\RF QOL.exe"
  CreateShortcut "$DESKTOP\${APP_SHORTCUT_NAME}.lnk" "$INSTDIR\RF QOL.exe"
!endif
SectionEnd

Section "Uninstall"
!ifndef DEV_SMOKE
  Delete "$DESKTOP\${APP_SHORTCUT_NAME}.lnk"
  Delete "$SMPROGRAMS\Karvalho\${APP_SHORTCUT_NAME}.lnk"
  RMDir "$SMPROGRAMS\Karvalho"
!endif
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\RF QOL.exe"
  Delete "$INSTDIR\requirements-lock-win-x64-py313.txt"
  Delete "$INSTDIR\sbom-python.json"
  Delete "$INSTDIR\Uninstall.exe"
!ifndef DEV_SMOKE
  DeleteRegKey HKLM "${APP_REGKEY}"
  DeleteRegKey HKLM "${APP_UNINSTALL_KEY}"
!endif
SectionEnd
