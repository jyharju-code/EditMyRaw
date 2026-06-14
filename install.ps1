# EditMyRaw one-line installer for Windows (PowerShell).
#   irm https://raw.githubusercontent.com/jyharju-code/EditMyRaw/main/install.ps1 | iex
#
# Uses `uv` to fetch a managed Python and all dependencies (~200 MB, one time)
# and creates a double-click launcher on your Desktop.

$ErrorActionPreference = "Stop"
Write-Host ">  Installing EditMyRaw..."

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "   Installing uv (one-time)..."
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
  $env:Path = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;$env:Path"
}

$AppDir  = "$env:USERPROFILE\.editmyraw-app"
$Tarball = "https://github.com/jyharju-code/EditMyRaw/archive/refs/heads/main.tar.gz"

Write-Host "   Creating environment in $AppDir..."
if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
uv venv --python 3.12 "$AppDir\.venv"
$Py = "$AppDir\.venv\Scripts\python.exe"

Write-Host "   Downloading and installing dependencies (~200 MB, one time)..."
uv pip install --python "$Py" "editmyraw[desktop] @ $Tarball"

$Launcher = "$env:USERPROFILE\Desktop\EditMyRaw.cmd"
"@echo off`r`n`"$Py`" -m editmyraw.cli web" | Set-Content -Encoding ASCII $Launcher

Write-Host ""
Write-Host "OK  Installed."
Write-Host "    -> Double-click 'EditMyRaw.cmd' on your Desktop to start it."
Write-Host "    -> Add a free Gemini API key in the app (Settings). Get one at"
Write-Host "       https://aistudio.google.com/apikey"

if ($env:EDITMYRAW_NO_LAUNCH -ne "1") {
  Write-Host "Launching EditMyRaw now..."
  & $Py -m editmyraw.cli web
}
