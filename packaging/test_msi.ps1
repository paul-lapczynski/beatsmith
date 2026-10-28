param([Parameter(Mandatory=$true)][string]$MsiPath)
$ErrorActionPreference = 'Stop'
# This test installs/uninstalls only on a disposable GitHub runner.
if ($env:GITHUB_ACTIONS -ne 'true' -or -not $env:RUNNER_TEMP) {
    throw 'Run this installer test only on a disposable GitHub Actions runner.'
}
$msi = (Resolve-Path -LiteralPath $MsiPath).Path
$testRoot = Join-Path $env:RUNNER_TEMP ('beatsmith-msi-' + [guid]::NewGuid())
$blocked = Join-Path $testRoot 'blocked'
$installed = Join-Path $testRoot 'installed'
New-Item -ItemType Directory -Path (Join-Path $blocked '_internal') -Force | Out-Null
$sentinel = Join-Path $blocked '_internal\_socket.pyd'
Set-Content -LiteralPath $sentinel -Value 'legacy runtime fixture'
$sentinelHash = (Get-FileHash -LiteralPath $sentinel).Hash
$keyName = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6C1C5E57-3F4B-4D8C-9E61-5A0D2B7F7C11}_is1'

function Invoke-TestMsi([string[]]$MsiArguments) {
    $process = Start-Process -FilePath msiexec.exe -ArgumentList $MsiArguments -WindowStyle Hidden -Wait -PassThru
    return $process.ExitCode
}

function With-LegacyEntry([string]$View, [string]$DisplayName, [scriptblock]$Check) {
    $registry = [Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', $View)
    $existing = $registry.OpenSubKey($keyName)
    if ($null -ne $existing) {
        $existing.Close()
        $registry.Close()
        throw "Refusing to replace an existing uninstall registration ($View)."
    }
    $created = $false
    try {
        $key = $registry.CreateSubKey($keyName)
        $created = $true
        $key.SetValue('DisplayName', $DisplayName)
        $key.SetValue('UninstallString', 'fixture-only-not-an-uninstaller')
        $key.Close()
        & $Check
    } finally {
        if ($created) { $registry.DeleteSubKey($keyName) }
        $registry.Close()
    }
}

# Exercise the compiled MSI, not a copied version of its condition.
foreach ($view in @('Registry64', 'Registry32')) {
    foreach ($display in @('BeatSmith version 1.0.0', 'stepgen')) {
        With-LegacyEntry $view $display {
            $log = Join-Path $testRoot "blocked-$view-$($display.Replace(' ', '-')).log"
            $code = Invoke-TestMsi @('/i', "`"$msi`"", '/qn', '/norestart', "INSTALLFOLDER=`"$blocked`"", '/L*v', "`"$log`"")
            if ($code -ne 1603) { throw "Legacy EXE install was not blocked: $view / $display / $code" }
            if ((Get-Content -LiteralPath $log -Raw) -notmatch 'An earlier setup.exe installation') {
                throw "MSI failed for an unexpected reason. See $log"
            }
            if ((Get-FileHash -LiteralPath $sentinel).Hash -ne $sentinelHash) {
                throw 'Blocked installer changed the legacy runtime.'
            }
            Write-Host "PASS: blocked $display ($view) before touching runtime files"
        }
    }
}

$didInstall = $false
try {
    $code = Invoke-TestMsi @('/i', "`"$msi`"", '/qn', '/norestart', "INSTALLFOLDER=`"$installed`"", '/L*v', "`"$(Join-Path $testRoot 'installed.log')`"")
    if ($code -notin @(0, 3010)) { throw "Clean MSI install failed: $code" }
    $didInstall = $true
    python "$PSScriptRoot/smoke_app.py" (Join-Path $installed 'BeatSmith.exe')
    if ($LASTEXITCODE -ne 0) { throw 'The MSI-installed app failed startup.' }

    # Users with a mixed installation must still be able to uninstall the MSI.
    With-LegacyEntry 'Registry64' 'BeatSmith version 1.0.0' {
        $code = Invoke-TestMsi @('/x', "`"$msi`"", '/qn', '/norestart', '/L*v', "`"$(Join-Path $testRoot 'uninstalled.log')`"")
        if ($code -notin @(0, 3010)) { throw "MSI uninstall with legacy entry failed: $code" }
    }
    $didInstall = $false
    Write-Host 'PASS: clean installed app starts; mixed-registration uninstall remains possible'
} finally {
    if ($didInstall) {
        $code = Invoke-TestMsi @('/x', "`"$msi`"", '/qn', '/norestart')
        if ($code -notin @(0, 3010)) { throw "Test install cleanup failed: $code" }
    }
}
