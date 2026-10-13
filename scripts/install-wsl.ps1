#Requires -RunAsAdministrator
param()

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskLogDirectory = Join-Path $taskRoot '.local'
New-Item -ItemType Directory -Path $taskLogDirectory -Force | Out-Null
$taskStatusPath = Join-Path $taskLogDirectory 'wsl-install-status.json'
Start-Transcript -Path (Join-Path $taskLogDirectory 'wsl-install.log') -Append | Out-Null
try {
    $taskWinget = Get-Command winget -ErrorAction Stop
    & $taskWinget.Source install --id Microsoft.WSL --exact --source winget --silent --disable-interactivity --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        # winget also returns nonzero when the requested version is already installed.
        & wsl --version | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'WSL installation failed. See wsl-install.log.' }
    }
    $taskFeature = Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
    $taskRestartNeeded = $taskFeature.State -eq 'EnablePending'
    if ($taskFeature.State -eq 'Disabled') {
        $taskResult = Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All -NoRestart
        $taskRestartNeeded = $taskResult.RestartNeeded
    }
    @{ status = 'installed'; restart_required = [bool]$taskRestartNeeded } |
        ConvertTo-Json | Set-Content -LiteralPath $taskStatusPath -Encoding UTF8
} catch {
    @{ status = 'failed'; reason = $_.Exception.Message } |
        ConvertTo-Json | Set-Content -LiteralPath $taskStatusPath -Encoding UTF8
    throw
} finally {
    Stop-Transcript | Out-Null
}
