param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('x86', 'x64', 'arm64')]
    [string] $Arch
)

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) {
    throw 'vswhere.exe was not found on the GitHub runner'
}
$component = if ($Arch -eq 'arm64') {
    'Microsoft.VisualStudio.Component.VC.Tools.ARM64'
} else {
    'Microsoft.VisualStudio.Component.VC.Tools.x86.x64'
}
$installation = & $vswhere -latest -products * -requires $component -property installationPath
if (-not $installation) {
    throw 'A Visual Studio installation with the C++ toolchain was not found'
}
$launcher = Join-Path $installation 'Common7\Tools\Launch-VsDevShell.ps1'
if (-not (Test-Path $launcher)) {
    throw 'Launch-VsDevShell.ps1 was not found in Visual Studio'
}
# Visual Studio's ARM64 tools are cross-hosted by the AMD64 compiler even on
# GitHub's native Windows-on-ARM runner. Launch-VsDevShell accepts arm64 as a
# target architecture, but HostArch is deliberately limited to x86/amd64.
& $launcher -Arch $Arch -HostArch amd64 -SkipAutomaticLocation
if ($LASTEXITCODE -ne 0) {
    throw "Visual Studio developer shell setup failed for $Arch"
}
