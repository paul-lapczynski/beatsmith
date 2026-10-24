; Inno Setup script for the BeatSmith app. Built by build.bat; see BUILD.md.
#define AppVersion GetEnv("BEATSMITH_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.1"
#endif

[Setup]
AppId={{6C1C5E57-3F4B-4D8C-9E61-5A0D2B7F7C11}
AppName=BeatSmith
AppVersion={#AppVersion}
AppPublisher=BeatSmith
DefaultDirName={autopf}\BeatSmith
DefaultGroupName=BeatSmith
; installs over a stepgen 0.0.x install go in the new BeatSmith folder
UsePreviousAppDir=no
UsePreviousGroup=no
OutputDir=dist
OutputBaseFilename=BeatSmith-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\BeatSmith.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\BeatSmith\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\BeatSmith"; Filename: "{app}\BeatSmith.exe"
Name: "{group}\Uninstall BeatSmith"; Filename: "{uninstallexe}"
Name: "{autodesktop}\BeatSmith"; Filename: "{app}\BeatSmith.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BeatSmith.exe"; Description: "Start BeatSmith"; Flags: nowait postinstall skipifsilent
