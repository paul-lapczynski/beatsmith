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

const
  UpgradeCode = '{6C1C5E57-3F4B-4D8C-9E61-5A0D2B7F7C11}';
  OldKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6C1C5E57-3F4B-4D8C-9E61-5A0D2B7F7C11}_is1';

var
  OldExeUser, OldExeAll, HadStepgen: Boolean;
  OldMsis: TStringList;          // MSI installs of stepgen or BeatSmith (the MSIs' UpgradeCode is our AppId)

function IsOldExe(Root: Integer): Boolean;
var
  Name: String;
begin
  Result := RegQueryStringValue(Root, OldKey, 'DisplayName', Name) and (CompareText(Name, 'stepgen') = 0);
end;

// What an earlier install left in its own place: a stepgen setup.exe install
// (same AppId, but in the old stepgen folder, so installing over it would
// leave those files behind) and MSI installs, which Inno can't upgrade.
procedure FindOld;
var
  Installer, Related: Variant;
  I: Integer;
begin
  OldMsis := TStringList.Create;
  OldExeUser := IsOldExe(HKCU);
  OldExeAll := IsOldExe(HKLM);
  HadStepgen := OldExeUser or OldExeAll;
  try
    Installer := CreateOleObject('WindowsInstaller.Installer');
    Related := Installer.RelatedProducts(UpgradeCode);
    for I := 0 to Related.Count - 1 do begin
      OldMsis.Add(Related.Item(I));
      if CompareText(Installer.ProductInfo(Related.Item(I), 'ProductName'), 'stepgen') = 0 then
        HadStepgen := True;
    end;
  except
  end;
end;

function InitializeSetup(): Boolean;
begin
  FindOld;
  Result := True;
  if HadStepgen then
    Result := SuppressibleMsgBox('Looks like you have stepgen, the old version of BeatSmith. ' +
      'It has to be removed before BeatSmith can be installed.' + #13#10#13#10 +
      'Your songs, settings and add-ons are kept: BeatSmith picks them up the first time it starts.' +
      #13#10#13#10 + 'Remove stepgen and continue?', mbConfirmation, MB_YESNO, IDYES) = IDYES;
end;

procedure RunUninstaller(Root: Integer);
var
  Cmd: String;
  Code: Integer;
begin
  if RegQueryStringValue(Root, OldKey, 'UninstallString', Cmd) then
    Exec(RemoveQuotes(Cmd), '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  I, Code: Integer;
begin
  Result := '';
  if (OldExeAll or (OldMsis.Count > 0)) and not IsAdminInstallMode then begin
    Result := 'The old version is installed for everyone on this PC, so removing it needs administrator ' +
              'rights. Run this installer again and choose to install for all users.';
    exit;
  end;
  if OldExeUser then
    RunUninstaller(HKCU);
  if OldExeAll then
    RunUninstaller(HKLM);
  for I := 0 to OldMsis.Count - 1 do
    Exec(ExpandConstant('{sys}\msiexec.exe'), '/x ' + OldMsis[I] + ' /qn /norestart', '',
         SW_HIDE, ewWaitUntilTerminated, Code);
end;
