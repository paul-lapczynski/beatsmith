param([Parameter(Mandatory=$true)][string]$ExePath)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/addon-fixtures.ps1"
$setup = (Resolve-Path -LiteralPath $ExePath).Path
$testRoot = Join-Path $env:RUNNER_TEMP ('beatsmith-exe-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $testRoot | Out-Null
$installed = Join-Path $testRoot 'installed'
function Invoke-Setup {
    $p = Start-Process -FilePath $setup -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', "/DIR=`"$installed`"") -WindowStyle Hidden -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "EXE installation failed: $($p.ExitCode)" }
}
try {
    New-AddonFixtures
    Invoke-Setup
    Assert-AddonsKept
    Invoke-Setup
    Assert-AddonsKept
    python "$PSScriptRoot/../../packaging/smoke_app.py" (Join-Path $installed 'BeatSmith.exe')
    if ($LASTEXITCODE -ne 0) { throw 'EXE-installed app failed startup.' }
    Write-Host 'PASS: EXE installation/update preserves downloaded add-ons'
    $p = Start-Process -FilePath (Join-Path $installed 'unins000.exe') -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -WindowStyle Hidden -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "EXE uninstall failed: $($p.ExitCode)" }
    Assert-AddonsRemoved
    Write-Host 'PASS: EXE uninstall removes nested add-ons and preserves neighboring user data'
} finally {
    $uninstall = Join-Path $installed 'unins000.exe'
    if (Test-Path -LiteralPath $uninstall) {
        Start-Process -FilePath $uninstall -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -WindowStyle Hidden -Wait | Out-Null
    }
    Clear-AddonFixtures
}
