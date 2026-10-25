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
UsedUserAreasWarning=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "clean"; Description: "Clean install: forget settings and saved profiles from earlier versions (songs, song data and add-ons are kept)"; Flags: unchecked

[Registry]
; the app clears what earlier versions left the first time it starts
; (beatsmith_app.clean_install); the install time makes each clean install count once
Root: HKA; Subkey: "Software\BeatSmith"; ValueType: string; ValueName: "clean"; ValueData: "{code:InstallTime}"; Flags: uninsdeletevalue; Tasks: clean
Root: HKA; Subkey: "Software\BeatSmith"; ValueType: none; ValueName: "clean"; Flags: deletevalue; Tasks: not clean

[Files]
Source: "dist\BeatSmith\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\BeatSmith"; Filename: "{app}\BeatSmith.exe"
Name: "{group}\Uninstall BeatSmith"; Filename: "{uninstallexe}"
Name: "{autodesktop}\BeatSmith"; Filename: "{app}\BeatSmith.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BeatSmith.exe"; Description: "Start BeatSmith"; Flags: nowait postinstall skipifsilent

[Code]
function InstallTime(Param: String): String;
begin
  Result := GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':');
end;
