#define AppName "RF NEXT INFO"
#define AppVersion "0.1.6"
#define AppPublisher "Karvalho"
#define AppExeName "RFNextInfo.exe"

[Setup]
AppId={{D7D80FD7-0E48-4D45-9D88-20CB00B39AE3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://karvalho.dev.br/
DefaultDirName={autopf}\Karvalho\RF NEXT INFO
DefaultGroupName=Karvalho
OutputDir=..\dist
OutputBaseFilename=RFNextInfo-Setup-0.1.6-pilot
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\RFNextInfo.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Karvalho\RF NEXT INFO"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\RF NEXT INFO"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir RF NEXT INFO"; Flags: nowait postinstall skipifsilent
