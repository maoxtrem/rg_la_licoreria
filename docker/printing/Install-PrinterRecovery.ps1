$ErrorActionPreference = 'Stop'
$taskName = 'RG La Licoreria - Recuperar impresora USB'
$directory = Join-Path $env:LOCALAPPDATA 'RGLaLicoreria'
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$script = Join-Path $directory 'Watch-Printer.ps1'
Copy-Item (Join-Path $PSScriptRoot 'Watch-Printer.ps1') $script -Force
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $user
# A logon trigger alone cannot recover a monitor stopped during the session.
# IgnoreNew keeps this watchdog from starting a second running monitor.
$watchdogTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) { Stop-ScheduledTask -TaskName $taskName }
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($logonTrigger, $watchdogTrigger) -Principal $principal -Settings $settings -Description 'Reconecta exclusivamente la SAT Q23T UE a WSL tras apagarla o desconectarla.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
