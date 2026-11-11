$ErrorActionPreference = 'Stop'
$taskName = 'RG La Licoreria - Recuperar impresora USB'
$directory = Join-Path $env:LOCALAPPDATA 'RGLaLicoreria'
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$script = Join-Path $directory 'Watch-Printer.ps1'
Copy-Item (Join-Path $PSScriptRoot 'Watch-Printer.ps1') $script -Force
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Reconecta exclusivamente la SAT Q23T UE a WSL tras apagarla o desconectarla.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
