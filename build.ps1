# Builds dist\GublanStudio.exe and dist\GublanStudioSetup.exe for a release.
# The version always comes from studio\version.py, so the program, the installer and the GitHub tag agree.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1            # test, build and package
#   powershell -ExecutionPolicy Bypass -File build.ps1 -SkipTests

param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# python tools log to stderr. windows powershell turns that into errors when the output is redirected
# (for example `.\build.ps1 *> build.log`), so tools run with "Continue" and their exit codes are checked instead.
function Invoke-Tool([string]$Tool, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Tool @Arguments
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Stop-Build([string]$Message) {
    Write-Host ""
    Write-Host "build failed: $Message" -ForegroundColor Red
    exit 1
}

$versionLine = Select-String -LiteralPath "studio\version.py" -Pattern '^VERSION\s*=\s*"([0-9]+(\.[0-9]+)*)"' |
    Select-Object -First 1
if ($null -eq $versionLine) {
    Stop-Build "studio\version.py has no VERSION line"
}
$version = $versionLine.Matches[0].Groups[1].Value
Write-Host "building gublan studio $version" -ForegroundColor Cyan

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if ($null -eq $iscc) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        $iscc = $command.Source
    }
}
if ($null -eq $iscc) {
    Stop-Build "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php"
}

if (-not $SkipTests) {
    Write-Host "running the tests" -ForegroundColor Cyan
    $env:SDL_VIDEODRIVER = "dummy"
    $env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
    Invoke-Tool py @("-m", "unittest", "discover", "-s", "tests")
    if ($LASTEXITCODE -ne 0) {
        Stop-Build "the tests failed"
    }
}

Write-Host "building dist\GublanStudio.exe" -ForegroundColor Cyan
Invoke-Tool py @("-m", "PyInstaller", "--noconfirm", "--distpath", "dist", "--workpath", "build\GublanStudio",
    "GublanStudio.spec")
if ($LASTEXITCODE -ne 0) {
    Stop-Build "PyInstaller failed"
}
$programVersion = (Get-Item -LiteralPath "dist\GublanStudio.exe").VersionInfo.ProductVersion
if ($programVersion -ne $version) {
    Stop-Build "dist\GublanStudio.exe says it is version '$programVersion', not $version"
}

Write-Host "building dist\GublanStudioSetup.exe" -ForegroundColor Cyan
Invoke-Tool $iscc @("/Q", "/DMyAppVersion=$version", "GublanStudio.iss")
if ($LASTEXITCODE -ne 0) {
    Stop-Build "Inno Setup failed"
}
$setup = Get-Item -LiteralPath "dist\GublanStudioSetup.exe"
$setupVersion = $setup.VersionInfo.ProductVersion
if ($setupVersion -notlike "$version*") {
    Stop-Build "dist\GublanStudioSetup.exe says it is version '$setupVersion', not $version"
}

$hash = (Get-FileHash -LiteralPath $setup.FullName -Algorithm SHA256).Hash.ToLower()
$size = [math]::Round($setup.Length / 1MB, 1)
Write-Host ""
Write-Host "done: dist\GublanStudioSetup.exe ($size MB)" -ForegroundColor Green
Write-Host "  version: $version"
Write-Host "  sha256:  $hash"
Write-Host ""
Write-Host "to release it, create a GitHub release tagged exactly $version and attach"
Write-Host "dist\GublanStudioSetup.exe without renaming it."
