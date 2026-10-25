; Inno Setup script for the stepgen app. Built by build.bat; see BUILD.md.
#define AppVersion GetEnv("STEPGEN_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.1"
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
UsedUserAreasWarning=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "clean"; Description: "Clean install: forget settings and saved profiles from earlier versions (songs, song data and add-ons are kept)"; Flags: unchecked

[Registry]
; the app clears what earlier versions left the first time it starts
; (stepgen_app.clean_install); the install time makes each clean install count once
Root: HKA; Subkey: "Software\stepgen"; ValueType: string; ValueName: "clean"; ValueData: "{code:InstallTime}"; Flags: uninsdeletevalue; Tasks: clean
Root: HKA; Subkey: "Software\stepgen"; ValueType: none; ValueName: "clean"; Flags: deletevalue; Tasks: not clean

[Files]
Source: "dist\stepgen\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\stepgen"; Filename: "{app}\stepgen.exe"
Name: "{group}\Uninstall stepgen"; Filename: "{uninstallexe}"
Name: "{autodesktop}\stepgen"; Filename: "{app}\stepgen.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\stepgen.exe"; Description: "Start stepgen"; Flags: nowait postinstall skipifsilent

[Code]
function InstallTime(Param: String): String;
begin
  Result := GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':');
end;
