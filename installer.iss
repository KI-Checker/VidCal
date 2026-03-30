[Setup]
AppName=VidCal Video Calibration Tool
AppVersion=1.0
AppPublisher=IT-Checker
AppPublisherURL=https://github.com/KI-Checker/VidCal
DefaultDirName={autopf}\VidCal
DefaultGroupName=VidCal
OutputDir=Output
OutputBaseFilename=VidCal-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Files]
; Hauptprogramm inkl. gebündeltem FFmpeg (in dist\vidcal\ffmpeg\)
Source: "dist\vidcal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\VidCal — Video Calibration"; Filename: "{app}\vidcal.exe"
Name: "{commondesktop}\VidCal"; Filename: "{app}\vidcal.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Zusätzliche Symbole:"

[Run]
Filename: "{app}\vidcal.exe"; Description: "VidCal jetzt starten"; Flags: nowait postinstall skipifsilent
