#define ProductName "Acompanhamento Eleitoral CE 2026"
#define ProductVersion "1.0.0"

[Setup]
AppId={{DCD096F8-6BB3-43A5-90F5-64C25B4F1B64}
AppName={#ProductName}
AppVersion={#ProductVersion}
AppPublisher=CE2026Dashboard
DefaultDirName={localappdata}\Programs\CE2026Dashboard
DefaultGroupName={#ProductName}
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=CE2026Dashboard-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
Uninstallable=yes

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "..\dist\CE2026Dashboard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#ProductName}"; Filename: "{app}\CE2026Dashboard.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#ProductName}"; Filename: "{app}\CE2026Dashboard.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\CE2026Dashboard.exe"; Description: "Abrir o painel"; Flags: nowait postinstall skipifsilent
