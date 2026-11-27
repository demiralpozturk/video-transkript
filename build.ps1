# Video Transkript derleme betiği
#   powershell -ExecutionPolicy Bypass -File build.ps1          -> dist\VideoTranskript\VideoTranskript.exe
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Kisayol -> + masaüstü kısayolu
param([switch]$Kisayol)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) {
    py -3.12 -m venv .venv 2>$null; if (-not (Test-Path .venv)) { python -m venv .venv }
    .\.venv\Scripts\python -m pip install --upgrade pip
    .\.venv\Scripts\python -m pip install -r requirements.txt pyinstaller
}
.\.venv\Scripts\python araclar\ikon_uret.py
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean VideoTranskript.spec
$exe = Join-Path $PSScriptRoot 'dist\VideoTranskript\VideoTranskript.exe'
if (-not (Test-Path $exe)) { throw "Derleme başarısız: $exe yok" }
Write-Host "Hazır: $exe"
if ($Kisayol) {
    $masaustu = [Environment]::GetFolderPath('Desktop')
    $ws = New-Object -ComObject WScript.Shell
    $k = $ws.CreateShortcut((Join-Path $masaustu 'Video Transkript.lnk'))
    $k.TargetPath = $exe
    $k.WorkingDirectory = Split-Path $exe
    $k.IconLocation = "$exe,0"
    $k.Description = 'Video Transkript — Demiralp Öztürk'
    $k.Save()
    Write-Host "Masaüstü kısayolu: $(Join-Path $masaustu 'Video Transkript.lnk')"
}
