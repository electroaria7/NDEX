#define MyAppName "NDEX"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "NDEX"
#define MyAppExeName "NDEX_Launcher.exe"
#define ReleaseFolder "..\release\NDEX_v1.0.1"

[Setup]
AppId={{8F2C4A91-6D3E-4B17-9C58-1A7E0F4B2D90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\NDEX
DefaultGroupName=NDEX
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=NDEX_Setup_1.0.1
SetupIconFile=..\assets\branding\ndex_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"; LicenseFile: "..\TERMS.md"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"; LicenseFile: "..\TERMS.ko.md"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: "{#ReleaseFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\NDEX Launcher"; Filename: "{app}\NDEX_Launcher.exe"; Comment: "Photo workflow hub"
Name: "{group}\1. Backup - NDEX One"; Filename: "{app}\Apps\NDEX_One.exe"
Name: "{group}\2. Select & Rate - Image Manager"; Filename: "{app}\Apps\NDEX_Image_Manager.exe"
Name: "{group}\3. Extract - Auto Selector"; Filename: "{app}\Apps\NDEX_Auto_Selector.exe"
Name: "{group}\4. Frame & Export - NDEX Frame"; Filename: "{app}\Apps\NDEX_Frame.exe"
Name: "{group}\Docs"; Filename: "{app}\Docs"
Name: "{autodesktop}\NDEX"; Filename: "{app}\NDEX_Launcher.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch NDEX"; Flags: nowait postinstall skipifsilent
