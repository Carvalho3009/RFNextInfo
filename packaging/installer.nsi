Unicode True
RequestExecutionLevel admin
Name "RF NEXT QOL"
!ifndef APP_VERSION
!define APP_VERSION "3.0.2"
!endif
!ifndef APP_SOURCE
!define APP_SOURCE "..\dist\RFNextInfo"
!endif
OutFile "..\dist\RFNextQOL-Setup-${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES64\Karvalho\RF NEXT QOL"
InstallDirRegKey HKLM "Software\Karvalho\RFNextInfo" "InstallDir"

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
  IfFileExists "$INSTDIR\RFNextInfo.exe" 0 done
retry:
  ClearErrors
  FileOpen $0 "$INSTDIR\RFNextInfo.exe" a
  IfErrors running
  FileClose $0
  Goto done
running:
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
    "Feche o RF NEXT QOL antes de continuar.$\r$\n$\r$\nSe houver captura ativa, cancele a instalação, pare a captura e aguarde a leitura. Depois tente novamente." \
    IDRETRY retry
  Abort
done:
FunctionEnd

Section "RF NEXT QOL" SEC_APP
  Call EnsureAppClosed
  Sleep 1500
  RMDir /r "$INSTDIR\_internal"
  SetOutPath "$INSTDIR"
  File /r "${APP_SOURCE}\*.*"
  SetShellVarContext all
  CreateDirectory "$INSTDIR\data"
  CreateDirectory "$INSTDIR\database"
  CreateDirectory "$INSTDIR\logs"
  CreateDirectory "$INSTDIR\cache"
  CreateDirectory "$INSTDIR\updates"
  CreateDirectory "$INSTDIR\Capturas"
  ClearErrors
  StrCpy $0 -1
  ExecWait '"$INSTDIR\RFNextInfo.exe" --self-test' $0
  IfErrors self_test_exec_failed
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
    "O teste do programa instalado falhou (código $0). Consulte o arquivo install.log e não abra o RF NEXT QOL."
  Abort
self_test_ok:
  WriteRegStr HKLM "Software\Karvalho\RFNextInfo" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Karvalho"
  Delete "$SMPROGRAMS\Karvalho\RF NEXT INFO.lnk"
  Delete "$DESKTOP\RF NEXT INFO.lnk"
  CreateShortcut "$SMPROGRAMS\Karvalho\RF NEXT QOL.lnk" "$INSTDIR\RFNextInfo.exe"
  CreateShortcut "$DESKTOP\RF NEXT QOL.lnk" "$INSTDIR\RFNextInfo.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\RF NEXT QOL.lnk"
  Delete "$SMPROGRAMS\Karvalho\RF NEXT QOL.lnk"
  RMDir "$SMPROGRAMS\Karvalho"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\RFNextInfo.exe"
  Delete "$INSTDIR\Uninstall.exe"
  DeleteRegKey HKLM "Software\Karvalho\RFNextInfo"
SectionEnd
