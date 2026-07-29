Unicode True
RequestExecutionLevel admin
Name "RF NEXT INFO"
OutFile "..\dist\RFNextInfo-Setup-1.0.9.exe"
InstallDir "$PROGRAMFILES64\Karvalho\RF NEXT INFO"
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
    "Feche o RF NEXT INFO antes de continuar.$\r$\n$\r$\nSe houver captura ativa, cancele a instalação, pare a captura e aguarde a leitura. Depois tente novamente." \
    IDRETRY retry
  Abort
done:
FunctionEnd

Section "RF NEXT INFO" SEC_APP
  Call EnsureAppClosed
  Sleep 1500
  RMDir /r "$INSTDIR\_internal"
  SetOutPath "$INSTDIR"
  File /r "..\dist\RFNextInfo\*.*"
  SetShellVarContext all
  CreateDirectory "$APPDATA\Karvalho\RFNextInfo\logs"
  ClearErrors
  StrCpy $0 -1
  ExecWait '"$INSTDIR\RFNextInfo.exe" --self-test' $0
  IfErrors self_test_exec_failed
  Goto self_test_log
self_test_exec_failed:
  StrCpy $0 -1
self_test_log:
  FileOpen $1 "$APPDATA\Karvalho\RFNextInfo\logs\install.log" a
  FileWrite $1 "version=1.0.9 self_test=$0$\r$\n"
  FileClose $1
  SetShellVarContext current
  StrCmp $0 0 self_test_ok
  MessageBox MB_OK|MB_ICONSTOP \
    "O teste do programa instalado falhou (código $0). Consulte o arquivo install.log e não abra o RF NEXT INFO."
  Abort
self_test_ok:
  WriteRegStr HKLM "Software\Karvalho\RFNextInfo" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Karvalho"
  CreateShortcut "$SMPROGRAMS\Karvalho\RF NEXT INFO.lnk" "$INSTDIR\RFNextInfo.exe"
  CreateShortcut "$DESKTOP\RF NEXT INFO.lnk" "$INSTDIR\RFNextInfo.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\RF NEXT INFO.lnk"
  Delete "$SMPROGRAMS\Karvalho\RF NEXT INFO.lnk"
  RMDir "$SMPROGRAMS\Karvalho"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "Software\Karvalho\RFNextInfo"
SectionEnd
