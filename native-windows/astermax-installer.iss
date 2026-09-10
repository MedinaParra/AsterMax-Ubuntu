#ifndef SourceDir
  #error SourceDir must point to the validated application package
#endif
[Setup]
AppId=AsterMax.Mechanical
AppName=AsterMax Mechanical
AppVersion=9.76
AppPublisher=AsterMax
DefaultDirName={localappdata}\Programs\AsterMax Mechanical
DefaultGroupName=AsterMax Mechanical
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputBaseFilename=AsterMax-Mechanical-C9.76-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AsterMax Mechanical.exe
DisableProgramGroupPage=yes
[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\AsterMax Mechanical"; Filename: "{app}\AsterMax Mechanical.exe"; WorkingDir: "{app}"
[Run]
Filename: "{app}\AsterMax Mechanical.exe"; Description: "Abrir AsterMax Mechanical"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}"
