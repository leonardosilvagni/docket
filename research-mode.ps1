# Research mode for Windows: open everything, close everything when OpenWhispr quits.
# Usage:  powershell -ExecutionPolicy Bypass -File research-mode.ps1          (start)
#         powershell -ExecutionPolicy Bypass -File research-mode.ps1 -Stop    (force stop)
# Not yet tested on a real Windows PC: check the OpenWhispr path below on first use.
param([switch]$Stop)
$Dir = $PSScriptRoot
Start-Transcript -Path (Join-Path $Dir 'research-mode.log') -Append | Out-Null

# --- settings
$OpenWhispr = "$env:LOCALAPPDATA\Programs\OpenWhispr\OpenWhispr.exe"
$DockerApp  = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
$VikunjaHost = 'research.localhost'
$EnvFile = Join-Path $Dir '.env'
if (Test-Path $EnvFile) {
  $line = Select-String -Path $EnvFile -Pattern '^VIKUNJA_HOST=(\S+)' | Select-Object -First 1
  if ($line) { $VikunjaHost = $line.Matches[0].Groups[1].Value }
}
$LmsCmd = Get-Command lms -ErrorAction SilentlyContinue
$Lms = if ($LmsCmd) { $LmsCmd.Source } else { "$env:USERPROFILE\.lmstudio\bin\lms.exe" }

function Compose { docker compose -f "$Dir\docker-compose.yml" -f "$Dir\docker-compose.windows.yml" --project-directory $Dir @args }
function Stop-LMStudio {
  if (Test-Path $Lms) { & $Lms unload --all; & $Lms server stop; & $Lms daemon down 2>$null }
}

if ($Stop) { Compose stop; Stop-LMStudio; Stop-Transcript | Out-Null; exit }

if (-not (Test-Path $OpenWhispr)) { Write-Host "OpenWhispr not found at $OpenWhispr"; Stop-Transcript | Out-Null; exit 1 }
if (Get-Process -Name OpenWhispr -ErrorAction SilentlyContinue) { Write-Host 'OpenWhispr is already running'; Stop-Transcript | Out-Null; exit }

# start Docker Desktop if needed and wait for it
docker info *> $null
if ($LASTEXITCODE -ne 0) {
  Start-Process $DockerApp
  for ($i = 0; $i -lt 60; $i++) { Start-Sleep 2; docker info *> $null; if ($LASTEXITCODE -eq 0) { break } }
}

Compose up -d
if (Test-Path $Lms) { & $Lms server start --port 1234 }
Start-Process "http://$VikunjaHost"
Start-Process -FilePath $OpenWhispr -Wait      # waits until OpenWhispr quits

# finish the last notes, then close everything
Compose stop inbox-helper
Compose run --rm --no-deps inbox-helper python -u /app/helper.py --drain
Compose stop
Stop-LMStudio
Stop-Transcript | Out-Null
