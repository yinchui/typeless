#define AppName "Typeless"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef RepoRoot
  #define RepoRoot "..\.."
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\installer"
#endif

[Setup]
AppId={{C9F4F992-A76A-4A89-B3B6-45FD75BC4AF8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Typeless
DefaultDirName={autopf}\Typeless
DefaultGroupName=Typeless
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\TypelessAgent.exe
OutputDir={#OutputDir}
OutputBaseFilename=Typeless-Setup-x64-v{#AppVersion}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "开机启动 Typeless"; Flags: unchecked

[Files]
Source: "{#RepoRoot}\dist\backend\TypelessService.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\dist\backend\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "TypelessService.exe"
Source: "{#RepoRoot}\dist\agent\TypelessAgent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Typeless\Typeless"; Filename: "{app}\TypelessAgent.exe"
Name: "{autoprograms}\Typeless\卸载 Typeless"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TypelessAgent"; ValueData: """{app}\TypelessAgent.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\TypelessAgent.exe"; Description: "启动 Typeless"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  RuntimeDir: string;
  Choice: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    RuntimeDir := ExpandConstant('{localappdata}\Typeless\runtime');
    if DirExists(RuntimeDir) then
    begin
      Choice := MsgBox('是否同时清理用户数据（设置、词典、历史记录）？', mbConfirmation, MB_YESNO);
      if Choice = IDYES then
        DelTree(RuntimeDir, True, True, True);
    end;
  end;
end;
