#define AppName "Relic Auditor"
#define AppVersion "0.8.2"
#define AppPublisher "Dracanus AI"
#define AppURL "https://relic-auditor.briandrichter.chatgpt.site"
#define BuildRoot GetEnv("RELIC_BUILD_ROOT")
#define SourceRoot GetEnv("RELIC_SOURCE_ROOT")
#define InstallerRoot GetEnv("RELIC_INSTALLER_ROOT")
#define OutputRoot GetEnv("RELIC_INSTALLER_OUTPUT")

[Setup]
AppId={{0B820351-4350-446C-A1B3-4790CE6CEAF3}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DefaultDirName={localappdata}\Programs\Relic Auditor
DefaultGroupName=Relic Auditor
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputRoot}
OutputBaseFilename=Relic-Auditor-Setup-0.8.2-x64
SetupIconFile={#InstallerRoot}\assets\relic-auditor.ico
WizardStyle=modern
WizardImageFile={#InstallerRoot}\assets\wizard-large.bmp
WizardSmallImageFile={#InstallerRoot}\assets\wizard-small.bmp
LicenseFile={#SourceRoot}\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
Uninstallable=yes
UninstallDisplayIcon={app}\Relic Auditor.exe
ChangesEnvironment=yes
SetupLogging=yes
AppMutex=DracanusAI.RelicAuditor.EvidenceConsole

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "addtopath"; Description: "Add the Relic command-line tool to my PATH"; GroupDescription: "Command line:"; Flags: checkedonce

[Files]
Source: "{#BuildRoot}\pyinstaller-dist\Relic Auditor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildRoot}\pyinstaller-dist\relic-cli\*"; DestDir: "{app}\cli"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Relic Auditor"; Filename: "{app}\Relic Auditor.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Relic Auditor"; Filename: "{app}\Relic Auditor.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Relic Auditor.exe"; Description: "Launch Relic Auditor"; Flags: nowait postinstall skipifsilent

[Code]
function NormalizedPath(Value: String): String;
begin
  Result := RemoveQuotes(Trim(Value));
  while (Length(Result) > 3) and (Result[Length(Result)] = '\') do
    Delete(Result, Length(Result), 1);
  Result := Uppercase(Result);
end;

function PathContains(ExistingPath, Entry: String): Boolean;
var
  Parts: TArrayOfString;
  Index: Integer;
begin
  Result := False;
  Parts := StringSplit(ExistingPath, [';'], stAll);
  for Index := 0 to GetArrayLength(Parts) - 1 do
    if NormalizedPath(Parts[Index]) = NormalizedPath(Entry) then
    begin
      Result := True;
      Exit;
    end;
end;

procedure AddToUserPath(Entry: String);
var
  ExistingPath: String;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', ExistingPath) then
    ExistingPath := '';
  if not PathContains(ExistingPath, Entry) then
  begin
    if (ExistingPath <> '') and (ExistingPath[Length(ExistingPath)] <> ';') then
      ExistingPath := ExistingPath + ';';
    RegWriteExpandStringValue(HKCU, 'Environment', 'Path', ExistingPath + Entry);
  end;
end;

procedure RemoveFromUserPath(Entry: String);
var
  ExistingPath, UpdatedPath: String;
  Parts: TArrayOfString;
  Index: Integer;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', ExistingPath) then
    Exit;
  Parts := StringSplit(ExistingPath, [';'], stAll);
  UpdatedPath := '';
  for Index := 0 to GetArrayLength(Parts) - 1 do
    if (Trim(Parts[Index]) <> '') and
       (NormalizedPath(Parts[Index]) <> NormalizedPath(Entry)) then
    begin
      if UpdatedPath <> '' then
        UpdatedPath := UpdatedPath + ';';
      UpdatedPath := UpdatedPath + Parts[Index];
    end;
  RegWriteExpandStringValue(HKCU, 'Environment', 'Path', UpdatedPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then
    AddToUserPath(ExpandConstant('{app}\cli'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RemoveFromUserPath(ExpandConstant('{app}\cli'));
end;
