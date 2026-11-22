#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "Gublan Studio"

[Setup]
AppId={{B7290A11-10F4-4B71-A834-3E8D47A1C602}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Gublan
DefaultDirName={localappdata}\Programs\Gublan Studio
DefaultGroupName=Gublan Studio
UninstallDisplayName=Gublan Studio
OutputDir=dist
OutputBaseFilename=GublanStudioSetup
PrivilegesRequired=lowest
CloseApplications=yes
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\GublanStudio.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Gublan Studio"; Filename: "{app}\GublanStudio.exe"
Name: "{autodesktop}\Gublan Studio"; Filename: "{app}\GublanStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GublanStudio.exe"; Description: "Launch Gublan Studio"; Flags: postinstall nowait skipifsilent
