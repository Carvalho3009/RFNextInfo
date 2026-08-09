Unicode True
!ifdef DEV_SMOKE
RequestExecutionLevel user
!else
RequestExecutionLevel admin
!endif
Name "RF QOL"
!ifndef APP_VERSION
!define APP_VERSION "1.0.0"
!endif
!ifndef APP_SOURCE
!define APP_SOURCE "..\dist\RF QOL"
!endif
!ifndef APP_OUTFILE
!define APP_OUTFILE "..\dist\RF QOL Setup ${APP_VERSION}.exe"
!endif
!ifndef APP_INSTALLDIR
!define APP_INSTALLDIR "$PROGRAMFILES64\Karvalho\RF QOL"
!endif
OutFile "${APP_OUTFILE}"
InstallDir "${APP_INSTALLDIR}"
!ifndef DEV_SMOKE
InstallDirRegKey HKLM "Software\Karvalho\RFQOL" "InstallDir"
!endif
SetCompressor /SOLID lzma
CRCCheck on

VIProductVersion "1.0.0.0"
VIAddVersionKey /LANG=1046 "ProductName" "RF QOL"
VIAddVersionKey /LANG=1046 "CompanyName" "Karvalho"
VIAddVersionKey /LANG=1046 "FileDescription" "Instalador do RF QOL"
VIAddVersionKey /LANG=1046 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1046 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1046 "LegalCopyright" "Karvalho"

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
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
  ExecShellWait "" "$INSTDIR\RF QOL.exe" "--self-test" SW_HIDE
  IfErrors self_test_exec_failed
  IfFileExists "$INSTDIR\logs\self-test.ok" self_test_ok_marker self_test_exec_failed
self_test_ok_marker:
  StrCpy $0 0
  Goto self_test_log
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
  WriteRegStr HKLM "Software\Karvalho\RFQOL" "InstallDir" "$INSTDIR"
!endif
!ifndef DEV_SMOKE
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL" "DisplayName" "RF QOL"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL" "Publisher" "Karvalho"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL" "URLInfoAbout" "https://karvalho.dev.br/"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL" "HelpLink" "https://discord.gg/D3hhdMgkj"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL" "DisplayIcon" "$INSTDIR\RF QOL.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL" "NoRepair" 1
  CreateDirectory "$SMPROGRAMS\Karvalho"
  CreateShortcut "$SMPROGRAMS\Karvalho\RF QOL.lnk" "$INSTDIR\RF QOL.exe"
  CreateShortcut "$DESKTOP\RF QOL.lnk" "$INSTDIR\RF QOL.exe"
!endif
SectionEnd

Section "Uninstall"
!ifndef DEV_SMOKE
  Delete "$DESKTOP\RF QOL.lnk"
  Delete "$SMPROGRAMS\Karvalho\RF QOL.lnk"
  RMDir "$SMPROGRAMS\Karvalho"
!endif
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\RF QOL.exe"
  Delete "$INSTDIR\requirements-lock-win-x64-py313.txt"
  Delete "$INSTDIR\sbom-python.json"
  Delete "$INSTDIR\Uninstall.exe"
!ifndef DEV_SMOKE
  DeleteRegKey HKLM "Software\Karvalho\RFQOL"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL"
!endif
SectionEnd
