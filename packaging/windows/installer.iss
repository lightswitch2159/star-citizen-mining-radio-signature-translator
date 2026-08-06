; Inno Setup script for SC RS Scanner.
; Produces a single SCRSScannerSetup.exe that end users double-click to
; install -- Start Menu shortcut, optional Desktop shortcut, and a proper
; uninstaller registered in Windows "Add/Remove Programs".
;
; Requires: Inno Setup (free) - https://jrsoftware.org/isinfo.php
; Requires: build.bat already run successfully (this reads its output).
;
; To build: open this file in the Inno Setup Compiler and click Compile,
; or run from command line:
;   iscc installer.iss

#define MyAppName "SC RS Scanner"
#define MyAppVersion "1.0"
#define MyAppExeName "SC RS Scanner.exe"
#define MySourceDir "dist\SC RS Scanner"

[Setup]
AppId={{B6C1E6B0-6E1A-4C34-9B8B-5C6C1E6B0F01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=SCRSScannerSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Standard user install (no admin required) - {autopf} automatically
; resolves to a per-user Program Files equivalent when PrivilegesRequired
; is "lowest", or the real Program Files when run as admin.
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent
