Unicode True
RequestExecutionLevel admin
Name "RF NEXT INFO"
OutFile "..\dist\RFNextInfo-Setup-0.1.3-pilot.exe"
InstallDir "$PROGRAMFILES64\Karvalho\RF NEXT INFO"
InstallDirRegKey HKLM "Software\Karvalho\RFNextInfo" "InstallDir"

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\RFNextInfo.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir RF NEXT INFO"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Section "RF NEXT INFO" SEC_APP
  SetOutPath "$INSTDIR"
  File "..\dist\RFNextInfo.exe"
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
  Delete "$INSTDIR\RFNextInfo.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "Software\Karvalho\RFNextInfo"
SectionEnd
