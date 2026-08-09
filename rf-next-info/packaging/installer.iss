#define AppName "RF NEXT QOL"
#define AppVersion "3.0.7"
#define AppPublisher "Karvalho"
#define AppExeName "RFNextInfo.exe"

[Setup]
AppId={{D7D80FD7-0E48-4D45-9D88-20CB00B39AE3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://karvalho.dev.br/
DefaultDirName={autopf}\Karvalho\RF NEXT QOL
DefaultGroupName=Karvalho
OutputDir=..\dist
OutputBaseFilename=RFNextQOL-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
CloseApplications=yes
CloseApplicationsFilter=RFNextInfo.exe
RestartApplications=no
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\RFNextInfo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\database"; Permissions: users-modify
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\cache"; Permissions: users-modify
Name: "{app}\updates"; Permissions: users-modify
Name: "{app}\Capturas"; Permissions: users-modify

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[InstallDelete]
Type: files; Name: "{autoprograms}\Karvalho\RF NEXT INFO.lnk"
Type: files; Name: "{autodesktop}\RF NEXT INFO.lnk"

[Icons]
Name: "{autoprograms}\Karvalho\RF NEXT QOL"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\RF NEXT QOL"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  LogPath: String;
begin
  if CurStep <> ssPostInstall then
    Exit;
  LogPath := ExpandConstant('{app}\logs\install.log');
  ForceDirectories(ExtractFileDir(LogPath));
  if not Exec(
    ExpandConstant('{app}\{#AppExeName}'),
    '--self-test',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
    ResultCode := -1;
  SaveStringToFile(
    LogPath,
    'version={#AppVersion} self_test=' + IntToStr(ResultCode) + #13#10,
    True
  );
  if ResultCode <> 0 then
    RaiseException(
      'O teste do programa instalado falhou. Consulte install.log.'
    );
end;
