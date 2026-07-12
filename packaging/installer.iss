; Inno Setup script for Framezy.
; Compiled by the GitHub Actions workflow (.github/workflows/build-windows.yml)
; via ISCC.exe. Expects dist\Framezy.exe to already exist (built by PyInstaller)
; and to be run from the repo root.

#define MyAppName "Framezy"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "AJ"
#define MyAppExeName "Framezy.exe"

[Setup]
AppId={{CC474B24-C4DF-4CEA-A03A-D750EDF5F017}
AppName={#MyAppName}
AppVerName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Framezy
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=FramezySetup
SetupIconFile=..\assets\icon.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\dist\Framezy.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
