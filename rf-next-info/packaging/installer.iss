#define AppName "RF QOL"
#define AppVersion "1.0.7"
#define AppPublisher "Karvalho"
#define AppExeName "RF QOL.exe"

[Setup]
AppId={{79802CC5-5EDE-4617-BDB9-DD897A08156E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://karvalho.dev.br/
DefaultDirName={autopf}\Karvalho\RF QOL
DefaultGroupName=Karvalho
OutputDir=..\dist
OutputBaseFilename=RF QOL Setup {#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
CloseApplications=yes
CloseApplicationsFilter=RF QOL.exe
RestartApplications=no
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\RF QOL\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\database"; Permissions: users-modify
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\cache"; Permissions: users-modify
Name: "{app}\Capturas"; Permissions: users-modify
Name: "{commonappdata}\Karvalho\RF QOL"; Permissions: admins-full; Flags: uninsneveruninstall
Name: "{commonappdata}\Karvalho\RF QOL\updates"; Permissions: admins-full; Flags: uninsneveruninstall

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Karvalho\RF QOL"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\RF QOL"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

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
