Unicode True
!ifdef DEV_SMOKE
RequestExecutionLevel user
!else
RequestExecutionLevel admin
!endif

!ifndef APP_VERSION
!define APP_VERSION "2.0.0-beta.35"
!endif
!ifndef APP_FILE_VERSION
!define APP_FILE_VERSION "2.0.0.45"
!endif
!ifndef APP_SOURCE
!define APP_SOURCE "..\dist\RF Next Companion"
!endif
!ifndef APP_OUTFILE
!define APP_OUTFILE "..\dist\RF Next Companion Setup ${APP_VERSION}.exe"
!endif
!ifndef APP_INSTALLDIR
!define APP_INSTALLDIR "$PROGRAMFILES64\Karvalho\RF Next Companion"
!endif

!define APP_DISPLAY_NAME "RF Next Companion Beta"
!define APP_REGKEY "Software\Karvalho\RFQOLAgent"
!define APP_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\RF QOL Agent"

Name "${APP_DISPLAY_NAME}"
OutFile "${APP_OUTFILE}"
InstallDir "${APP_INSTALLDIR}"
!ifndef DEV_SMOKE
InstallDirRegKey HKLM "${APP_REGKEY}" "InstallDir"
!endif
SetCompressor /SOLID lzma
CRCCheck on
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "${APP_FILE_VERSION}"
VIAddVersionKey /LANG=1046 "ProductName" "${APP_DISPLAY_NAME}"
VIAddVersionKey /LANG=1046 "CompanyName" "Karvalho"
VIAddVersionKey /LANG=1046 "FileDescription" "Instalador do RF Next Companion"
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
!define MUI_FINISHPAGE_RUN "$INSTDIR\RF Next Companion.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o RF Next Companion"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Function EnsureAgentClosed
  IfFileExists "$INSTDIR\RF Next Companion.exe" 0 checkLegacy
  Goto retryCurrent
checkLegacy:
  IfFileExists "$INSTDIR\RF QOL Agent.exe" 0 done
retryLegacy:
  ClearErrors
  FileOpen $0 "$INSTDIR\RF QOL Agent.exe" a
  IfErrors legacyRunning
  FileClose $0
  Goto done
retryCurrent:
  ClearErrors
  FileOpen $0 "$INSTDIR\RF Next Companion.exe" a
  IfErrors currentRunning
  FileClose $0
  Goto checkLegacy
currentRunning:
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
    "O RF Next Companion ainda está aberto.$\r$\n$\r$\nEncerre-o pela bandeja antes de continuar. A captura será finalizada normalmente e nenhum dado local será apagado." \
    IDRETRY retryCurrent
  Abort
legacyRunning:
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
    "O RF QOL Agent ainda está aberto.$\r$\n$\r$\nEncerre-o pela bandeja antes de continuar. A captura será finalizada normalmente e nenhum dado local será apagado." \
    IDRETRY retryLegacy
  Abort
done:
FunctionEnd

Section "RF Next Companion" SEC_APP
  Call EnsureAgentClosed
  SetOutPath "$INSTDIR"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\RF Next Companion.exe"
  Delete "$INSTDIR\RF QOL Agent.exe"
  File /r "${APP_SOURCE}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

!ifdef DEV_SMOKE
  SetShellVarContext current
!else
  SetShellVarContext all
  WriteRegStr HKLM "${APP_REGKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayName" "${APP_DISPLAY_NAME}"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "Publisher" "Karvalho"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "URLInfoAbout" "https://apirf.karvalho.dev.br/"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\RF Next Companion.exe"
  WriteRegStr HKLM "${APP_UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKLM "${APP_UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${APP_UNINSTALL_KEY}" "NoRepair" 1
  CreateDirectory "$SMPROGRAMS\Karvalho"
  Delete "$SMPROGRAMS\Karvalho\RF QOL Agent.lnk"
  Delete "$DESKTOP\RF QOL Agent.lnk"
  CreateShortcut "$SMPROGRAMS\Karvalho\RF Next Companion.lnk" "$INSTDIR\RF Next Companion.exe"
  CreateShortcut "$DESKTOP\RF Next Companion.lnk" "$INSTDIR\RF Next Companion.exe"
!endif
SectionEnd

Section "Uninstall"
  SetShellVarContext all
  Delete "$DESKTOP\RF QOL Agent.lnk"
  Delete "$DESKTOP\RF Next Companion.lnk"
  Delete "$SMPROGRAMS\Karvalho\RF QOL Agent.lnk"
  Delete "$SMPROGRAMS\Karvalho\RF Next Companion.lnk"
  RMDir "$SMPROGRAMS\Karvalho"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "RF QOL Agent"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "RF Next Companion"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\RF QOL Agent.exe"
  Delete "$INSTDIR\RF Next Companion.exe"
  Delete "$INSTDIR\Uninstall.exe"
!ifndef DEV_SMOKE
  DeleteRegKey HKLM "${APP_REGKEY}"
  DeleteRegKey HKLM "${APP_UNINSTALL_KEY}"
!endif
  RMDir "$INSTDIR"
  ; O histórico, a identidade DPAPI e a fila ficam em LocalAppData e são
  ; preservados para reinstalação ou recuperação deliberada pelo usuário.
SectionEnd
