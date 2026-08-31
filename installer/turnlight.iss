#define MyAppName "Turnlight"
#define MyAppVersion "0.9.1-beta"
#define MyAppPublisher "ivanislit"
#define MyAppExeName "Turnlight.exe"

[Setup]
AppId={{8F4EDE9B-40B4-4F74-8D99-0F2D59DF5506}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installer-output
OutputBaseFilename=Turnlight-{#MyAppVersion}-Setup
SetupIconFile=..\assets\app\turnlight.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut (recommended while you get used to Turnlight)"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "..\dist\Turnlight\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Messages]
SelectTasksDesc=Select the shortcuts to create. The desktop shortcut is recommended at first so Turnlight is easy to find while you build the habit.
