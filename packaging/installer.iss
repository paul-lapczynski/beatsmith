; Inno Setup script for the stepgen app. Built by build.bat; see BUILD.md.
#define AppVersion GetEnv("STEPGEN_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6C1C5E57-3F4B-4D8C-9E61-5A0D2B7F7C11}
AppName=stepgen
AppVersion={#AppVersion}
AppPublisher=stepgen
DefaultDirName={autopf}\stepgen
DefaultGroupName=stepgen
OutputDir=dist
OutputBaseFilename=stepgen-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\stepgen.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\stepgen\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\stepgen"; Filename: "{app}\stepgen.exe"
Name: "{group}\Uninstall stepgen"; Filename: "{uninstallexe}"
Name: "{autodesktop}\stepgen"; Filename: "{app}\stepgen.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\stepgen.exe"; Description: "Start stepgen"; Flags: nowait postinstall skipifsilent
