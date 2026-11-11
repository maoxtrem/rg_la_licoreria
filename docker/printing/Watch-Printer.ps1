param([switch]$Once)

$ErrorActionPreference = 'Stop'
$usbipd = Join-Path $env:ProgramFiles 'usbipd-win\usbipd.exe'
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
            & $usbipd attach --wsl Ubuntu-22.04 --hardware-id 2aaf:6015
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo adjuntar la impresora a WSL.' }
        }
    } catch {
        Write-Warning $_
        if ($Once) { exit 1 }
    }
    if (-not $Once) { Start-Sleep -Seconds 10 }
} while (-not $Once)
