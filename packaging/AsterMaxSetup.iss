#define MyAppName "AsterMax Mechanical"
#define MyAppVersion "0.6.2"
#define MyAppPublisher "AsterMax"
#define MyAppExeName "AsterMax.exe"

[Setup]
AppId={{6A8A6B94-6F2E-4D9A-8F6E-6B5D824D3B91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AsterMax Mechanical
DefaultGroupName=AsterMax Mechanical
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir=..\installer-dist
OutputBaseFilename=AsterMaxSetup-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ChangesEnvironment=no
SetupLogging=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\AsterMax\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "bootstrap_dependencies.ps1"; DestDir: "{app}\installer"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\AsterMax Mechanical"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\AsterMax Mechanical"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\bootstrap_dependencies.ps1"""; StatusMsg: "Comprobando e instalando dependencias de Windows…"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Parameters: "--self-test ""{localappdata}\AsterMax\packaged-self-test"""; StatusMsg: "Verificando el motor FEA empaquetado…"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar AsterMax Mechanical"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\installer"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsWin64 then
  begin
    MsgBox('AsterMax Mechanical requiere Windows de 64 bits.', mbError, MB_OK);
    Result := False;
  end;
end;
