; Inno Setup script. Build after PyInstaller:  iscc /DAppVersion=0.2.1 packaging\windows\pushbridge.iss
#ifndef AppVersion
  #define AppVersion "0.2.1"
#endif

[Setup]
AppId={{6C1E2B5A-4F0D-4E7B-9A51-5D2C8B7F0A11}
AppName=Push Bridge
AppVersion={#AppVersion}
AppPublisher=Fancy Butler
AppPublisherURL=https://github.com/fancy-butler/pushbridge
DefaultDirName={autopf}\Push Bridge
DefaultGroupName=Push Bridge
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=PushBridge-{#AppVersion}-windows-setup
SetupIconFile=pushbridge.ico
UninstallDisplayIcon={app}\PushBridge.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\..\dist\PushBridge\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Push Bridge"; Filename: "{app}\PushBridge.exe"
Name: "{autodesktop}\Push Bridge"; Filename: "{app}\PushBridge.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PushBridge.exe"; Description: "Start Push Bridge"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v PushBridge /f"; Flags: runhidden; RunOnceId: "RemoveAutostart"
