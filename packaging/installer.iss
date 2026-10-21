; Inno Setup 6 script for Wisp (DECISIONS.md D-037). Built by packaging\build.py:
;   ISCC /DAppVersion=<version> /DSourceDir=dist\Wisp /Odist packaging\installer.iss
; Per-user install (no administrator rights): %LOCALAPPDATA%\Programs\Wisp, Start-menu shortcuts
; (Wisp, Uninstall Wisp), optional desktop shortcut, optional start at sign-in (HKCU Run value "Wisp", the same value
; the app's own setting writes). Uninstall removes the program, shortcuts, the Run value and
; comtypes' empty cache folder, and asks whether to delete the user's data (default: keep).
; Sources: jrsoftware.org/ishelp — [Setup] PrivilegesRequired, AppMutex,
; ArchitecturesInstallIn64BitMode, [Registry] uninsdeletevalue, SuppressibleMsgBox,
; CurUninstallStepChanged, constants {autopf} {autoprograms} {userappdata} {%NAME}.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Wisp"
#endif

[Setup]
AppId={{6BEA9B52-61A0-4000-821A-467C83251EE0}
AppName=Wisp
AppVersion={#AppVersion}
AppVerName=Wisp {#AppVersion}
AppPublisher=Wisp
DefaultDirName={autopf}\Wisp
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
AppMutex=WispAssistantMutex
OutputBaseFilename=WispSetup-{#AppVersion}
SetupIconFile=wisp.ico
UninstallDisplayIcon={app}\Wisp.exe
UninstallDisplayName=Wisp
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start Wisp when I sign in to Windows"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Files from an older version that the new one no longer ships.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Wisp"; Filename: "{app}\Wisp.exe"
; {uninstallexe}: "typically used in an [Icons] section entry for creating an Uninstall icon" (D-061)
Name: "{autoprograms}\Uninstall Wisp"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Wisp"; Filename: "{app}\Wisp.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "Wisp"; ValueData: """{app}\Wisp.exe"" --background"; \
  Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\Wisp.exe"; Description: "Start Wisp now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; comtypes creates this (empty) folder when a frozen app imports comtypes.client.
Type: filesandordirs; Name: "{%TEMP}\comtypes_cache\Wisp-312"
Type: dirifempty; Name: "{%TEMP}\comtypes_cache"

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

procedure RemoveRunValue();
var
  Value: String;
begin
  { The app's "Start with Windows" setting may have written the value after installation. }
  if RegQueryStringValue(HKCU, RunKey, 'Wisp', Value) then
    if Pos(Lowercase(ExpandConstant('{app}')), Lowercase(Value)) > 0 then
      RegDeleteValue(HKCU, RunKey, 'Wisp');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
    RemoveRunValue();
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\Wisp');
    if DirExists(DataDir) then
      if SuppressibleMsgBox('Also delete your Wisp data (settings, API key, memories, ' +
           'to-dos, routines, clipboard history and logs) in ' + DataDir + '?',
           mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
