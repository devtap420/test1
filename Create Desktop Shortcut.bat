@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "$desktop = [Environment]::GetFolderPath('Desktop'); $ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut((Join-Path $desktop 'Jarvis.lnk')); $s.TargetPath = 'C:\Users\tapan\Documents\jar\start_jarvis.bat'; $s.WorkingDirectory = 'C:\Users\tapan\Documents\jar'; $s.Description = 'Start Jarvis'; $s.IconLocation = '%SystemRoot%\System32\shell32.dll,25'; $s.Save()"
if errorlevel 1 (
    echo Failed to create the shortcut.
) else (
    echo Shortcut "Jarvis" created on your Desktop.
)
pause
