; build with build.ps1, which passes /DMyAppVersion=<the VERSION in studio\version.py>.
; the version always comes from studio\version.py so the installer, the program and the github tag agree.
#define VersionFile AddBackslash(SourcePath) + "studio\version.py"
#define VersionHandle FileOpen(VersionFile)
#if !VersionHandle
  #error could not open studio\version.py
#endif
#define VersionLine ""
#sub ReadVersionLine
  #define public Line FileRead(VersionHandle)
  #if Pos("VERSION", Line) == 1
    #define public VersionLine Line
  #endif
#endsub
#for {0; !FileEof(VersionHandle) && VersionLine == ""; 0} ReadVersionLine
#expr FileClose(VersionHandle)
#if VersionLine == ""
  #error studio\version.py has no VERSION line
#endif
#define SourceVersion Copy(VersionLine, Pos('"', VersionLine) + 1, RPos('"', VersionLine) - Pos('"', VersionLine) - 1)

#ifndef MyAppVersion
  #define MyAppVersion SourceVersion
#endif
#if MyAppVersion != SourceVersion
  #error MyAppVersion does not match VERSION in studio\version.py
#endif

#define MyAppName "Gublan Studio"

[Setup]
AppId={{B7290A11-10F4-4B71-A834-3E8D47A1C602}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
AppPublisher=Gublan
DefaultDirName={localappdata}\Programs\Gublan Studio
DefaultGroupName=Gublan Studio
UninstallDisplayName=Gublan Studio
OutputDir=dist
OutputBaseFilename=GublanStudioSetup
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\GublanStudio.exe
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "gublfiles"; Description: "Open .gubl files with Gublan Studio, and add ""run with gublan"" to their right-click menu"; GroupDescription: "File types:"

[Registry]
; .gubl files: double-click opens them in the studio, right click > run with gublan starts them (GublanStudio.exe
; --run), and new > gublan program makes an empty one. studio\shell.py writes the same keys from
; tools > open .gubl files from explorer, for the portable exe.
Root: HKA; Subkey: "Software\Classes\.gubl"; ValueType: string; ValueName: ""; ValueData: "GublanStudio.gubl"; Flags: uninsdeletevalue; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\.gubl"; ValueType: string; ValueName: "Content Type"; ValueData: "text/plain"; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\.gubl"; ValueType: string; ValueName: "PerceivedType"; ValueData: "text"; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\.gubl\OpenWithProgids"; ValueType: string; ValueName: "GublanStudio.gubl"; ValueData: ""; Flags: uninsdeletevalue; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\.gubl\ShellNew"; ValueType: string; ValueName: "NullFile"; ValueData: ""; Flags: uninsdeletekey; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\GublanStudio.gubl"; ValueType: string; ValueName: ""; ValueData: "gublan program"; Flags: uninsdeletekey; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\GublanStudio.gubl\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\GublanStudio.exe,0"; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\GublanStudio.gubl\shell"; ValueType: string; ValueName: ""; ValueData: "open"; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\GublanStudio.gubl\shell\open"; ValueType: string; ValueName: ""; ValueData: "open in gublan studio"; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\GublanStudio.gubl\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\GublanStudio.exe"" ""%1"""; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\GublanStudio.gubl\shell\run"; ValueType: string; ValueName: ""; ValueData: "run with gublan"; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\GublanStudio.gubl\shell\run"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\GublanStudio.exe,0"; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\GublanStudio.gubl\shell\run\command"; ValueType: string; ValueName: ""; ValueData: """{app}\GublanStudio.exe"" --run ""%1"""; Tasks: gublfiles
Root: HKA; Subkey: "Software\Classes\Applications\GublanStudio.exe\SupportedTypes"; ValueType: string; ValueName: ".gubl"; ValueData: ""; Flags: uninsdeletekey

[Files]
Source: "dist\GublanStudio.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Gublan Studio"; Filename: "{app}\GublanStudio.exe"; IconFilename: "{app}\GublanStudio.exe"
Name: "{autodesktop}\Gublan Studio"; Filename: "{app}\GublanStudio.exe"; IconFilename: "{app}\GublanStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GublanStudio.exe"; Description: "Launch Gublan Studio"; Flags: postinstall nowait skipifsilent
; the in-app updater runs setup silently with /RELAUNCH=1 so the new version opens by itself afterwards
Filename: "{app}\GublanStudio.exe"; Flags: nowait; Check: ShouldRelaunch

[Code]
const
  SYNCHRONIZE = $00100000;
  WAIT_TIMEOUT = $00000102;

function OpenProcess(Access: DWORD; Inherit: BOOL; ProcessId: DWORD): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: DWORD): DWORD;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';
function SetEnvironmentVariable(Name: String; Value: String): BOOL;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';
{ the same call with a null value, which removes the variable }
function RemoveEnvironmentVariable(Name: String; Value: Cardinal): BOOL;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

{ wait for one gublan studio process (the one that started this update) to finish closing. }
procedure WaitForProcess(Pid: Integer);
var
  Handle: THandle;
begin
  if Pid <= 0 then
    exit;
  Handle := OpenProcess(SYNCHRONIZE, False, Pid);
  if Handle = 0 then
    exit;
  try
    if WaitForSingleObject(Handle, 60000) = WAIT_TIMEOUT then
      Log(Format('process %d is still running after 60 seconds', [Pid]));
  finally
    CloseHandle(Handle);
  end;
end;

function InitializeSetup(): Boolean;
var
  Pids: String;
  Part: String;
  Comma: Integer;
begin
  { programs this setup starts are fresh copies: drop anything a running gublan studio passed down to us. }
  SetEnvironmentVariable('PYINSTALLER_RESET_ENVIRONMENT', '1');
  RemoveEnvironmentVariable('_PYI_ARCHIVE_FILE', 0);
  RemoveEnvironmentVariable('_PYI_APPLICATION_HOME_DIR', 0);
  RemoveEnvironmentVariable('_PYI_PARENT_PROCESS_LEVEL', 0);
  RemoveEnvironmentVariable('_PYI_SPLASH_IPC', 0);

  Pids := ExpandConstant('{param:WAITPID|}');
  while Pids <> '' do
  begin
    Comma := Pos(',', Pids);
    if Comma = 0 then
    begin
      Part := Pids;
      Pids := '';
    end
    else
    begin
      Part := Copy(Pids, 1, Comma - 1);
      Delete(Pids, 1, Comma);
    end;
    WaitForProcess(StrToIntDef(Trim(Part), 0));
  end;
  Result := True;
end;

function ShouldRelaunch(): Boolean;
begin
  Result := WizardSilent() and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;
