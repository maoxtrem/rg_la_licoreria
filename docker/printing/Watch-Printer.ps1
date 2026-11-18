param([switch]$Once)

$ErrorActionPreference = 'Stop'
$usbipd = Join-Path $env:ProgramFiles 'usbipd-win\usbipd.exe'
$logPath = Join-Path $PSScriptRoot 'PrinterRecovery.log'
function Write-RecoveryLog([string]$Message) {
    try {
        if ((Test-Path $logPath) -and (Get-Item $logPath).Length -gt 1MB) {
            Move-Item $logPath "$logPath.old" -Force
        }
        Add-Content -Path $logPath -Value "$(Get-Date -Format o) $Message"
    } catch { Write-Warning "No se pudo escribir el registro: $_" }
}
Write-RecoveryLog 'Monitor iniciado.'
do {
    try {
        $state = (& $usbipd state | Out-String | ConvertFrom-Json)
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar usbipd.' }
        $printer = $state.Devices | Where-Object { $_.InstanceId -like 'USB\VID_2AAF&PID_6015\*' }
        if ($printer -and $printer.BusId -and -not $printer.ClientIPAddress) {
            if (-not $printer.PersistedGuid) {
                throw 'La impresora necesita usbipd bind desde PowerShell como administrador.'
            }
            & wsl.exe -d Ubuntu-22.04 --exec /bin/true
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar Ubuntu-22.04.' }
            & $usbipd attach --wsl Ubuntu-22.04 --hardware-id 2aaf:6015
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo adjuntar la impresora a WSL.' }
            Write-RecoveryLog 'Impresora adjuntada a WSL.'
        }
    } catch {
        Write-RecoveryLog "Error: $_"
        Write-Warning $_
        if ($Once) { exit 1 }
    }
    if (-not $Once) { Start-Sleep -Seconds 10 }
} while (-not $Once)
