# Used only by the installer tests on disposable CI runners. Never delete a
# pre-existing add-on directory: the fixtures own exactly the paths below.
if ($env:GITHUB_ACTIONS -ne 'true' -or -not $env:RUNNER_TEMP) {
    throw 'Add-on fixtures require a disposable GitHub Actions runner.'
}
$fixtureRoots = @()
$fixtureFiles = @()
function New-AddonFixtures {
    foreach ($name in @('BeatSmith', 'stepgen')) {
        $base = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA $name))
        $root = [IO.Path]::GetFullPath((Join-Path $base 'addons'))
        if ($root -ne "$base\addons" -or (Test-Path -LiteralPath $root)) {
            throw "Refusing to replace an existing add-on folder: $root"
        }
    }
    foreach ($name in @('BeatSmith', 'stepgen')) {
        $base = Join-Path $env:LOCALAPPDATA $name
        $root = Join-Path $base 'addons'
        $script:fixtureRoots += [IO.Path]::GetFullPath($root)
        foreach ($part in @('stems\python\Lib', 'stems\models\whisper', 'stems\cache\torch', 'stems\gpu')) {
            $folder = Join-Path $root $part
            New-Item -ItemType Directory -Path $folder -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $folder 'fixture.txt') -Value 'private download fixture'
        }
        $keep = Join-Path $base ('keep-' + [guid]::NewGuid() + '.txt')
        Set-Content -LiteralPath $keep -Value 'settings/song data fixture'
        $script:fixtureFiles += $keep
    }
}
function Assert-AddonsKept {
    foreach ($root in $fixtureRoots) {
        if (-not (Test-Path -LiteralPath (Join-Path $root 'stems\python\Lib\fixture.txt'))) {
            throw "An update removed add-ons: $root"
        }
    }
}
function Assert-AddonsRemoved {
    foreach ($root in $fixtureRoots) {
        if (Test-Path -LiteralPath $root) { throw "Uninstall left add-ons: $root" }
    }
    foreach ($keep in $fixtureFiles) {
        if ((Get-Content -LiteralPath $keep -Raw).Trim() -ne 'settings/song data fixture') {
            throw "Uninstall changed data outside add-ons: $keep"
        }
    }
}
function Clear-AddonFixtures {
    foreach ($root in $fixtureRoots) {
        $resolved = [IO.Path]::GetFullPath($root)
        $allowed = @('BeatSmith', 'stepgen') | ForEach-Object {
            [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "$_\addons"))
        }
        if ($resolved -notin $allowed) { throw "Unsafe fixture cleanup target: $resolved" }
        if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
    }
    foreach ($keep in $fixtureFiles) { Remove-Item -LiteralPath $keep -Force -ErrorAction SilentlyContinue }
}
