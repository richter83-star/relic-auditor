[CmdletBinding()]
param(
    [string]$SourceArchive = "",
    [string]$ExpectedSourceSha256 = "190740e2d8f2d30238858fe2085c48ea9e8aed873d6cb0b22b4bb6f8f70dc7bc",
    [string]$OutputDirectory = "",
    [string]$InnoSetupPath = "",
    [string]$SigningCertificate = "",
    [string]$SigningPassword = "",
    [switch]$KeepBuildDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$InstallerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$KitRoot = (Resolve-Path (Join-Path $InstallerRoot "..\..")).Path
if (-not $SourceArchive) {
    $SourceArchive = Join-Path $KitRoot "releases\relic-auditor-0.10.2.zip"
}
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $KitRoot "release-output"
}
$SourceArchive = (Resolve-Path $SourceArchive).Path
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$BuildRoot = Join-Path $KitRoot "build\windows"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $Command $($Arguments -join ' ')"
    }
}

function Get-PythonLauncher {
    $Py = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($Py) {
        return @{ Command = $Py.Source; Prefix = @("-3.12") }
    }
    $Python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($Python) {
        return @{ Command = $Python.Source; Prefix = @() }
    }
    throw "Python 3.12 is required to build the installer. The installed application will not require Python."
}

function Find-InnoSetup {
    param([string]$RequestedPath)
    if ($RequestedPath) {
        return (Resolve-Path $RequestedPath).Path
    }
    $Candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            return $Candidate
        }
    }
    $Command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }
    throw "Inno Setup 6 was not found. Install it or pass -InnoSetupPath."
}

function Find-SignTool {
    $Command = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }
    $SdkRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path -LiteralPath $SdkRoot) {
        $Candidate = Get-ChildItem -LiteralPath $SdkRoot -Filter "signtool.exe" -Recurse -File |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($Candidate) {
            return $Candidate.FullName
        }
    }
    throw "A signing certificate was supplied, but signtool.exe was not found."
}

function Sign-File {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not $SigningCertificate) {
        return
    }
    $SignTool = Find-SignTool
    $Arguments = @(
        "sign", "/fd", "SHA256", "/td", "SHA256",
        "/tr", "http://timestamp.digicert.com",
        "/f", $SigningCertificate
    )
    if ($SigningPassword) {
        $Arguments += @("/p", $SigningPassword)
    }
    $Arguments += $Path
    Invoke-Checked -Command $SignTool -Arguments $Arguments
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw "Relic Auditor 0.10.2 supports 64-bit Windows only."
}

$ActualSourceHash = (Get-FileHash -LiteralPath $SourceArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualSourceHash -ne $ExpectedSourceSha256.ToLowerInvariant()) {
    throw "Frozen source hash mismatch. Expected $ExpectedSourceSha256 but found $ActualSourceHash."
}

$SafeBuildParent = [System.IO.Path]::GetFullPath((Join-Path $KitRoot "build"))
$SafeBuildRoot = [System.IO.Path]::GetFullPath($BuildRoot)
if (-not $SafeBuildRoot.StartsWith($SafeBuildParent, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to clean an unexpected build directory: $SafeBuildRoot"
}
if (Test-Path -LiteralPath $SafeBuildRoot) {
    Remove-Item -LiteralPath $SafeBuildRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $SafeBuildRoot | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$TestTempRoot = Join-Path $SafeBuildRoot "temp"
New-Item -ItemType Directory -Path $TestTempRoot | Out-Null
$env:TEMP = $TestTempRoot
$env:TMP = $TestTempRoot
Get-ChildItem -LiteralPath $OutputDirectory -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @(
        "Relic-Auditor-Setup-0.10.2-x64.exe",
        "SHA256SUMS.txt",
        "release-manifest.json",
        "INSTALLER-README.md"
    ) } |
    Remove-Item -Force

$UnpackedRoot = Join-Path $SafeBuildRoot "source-unpacked"
Expand-Archive -LiteralPath $SourceArchive -DestinationPath $UnpackedRoot -Force
$SourceRoot = Join-Path $UnpackedRoot "relic-auditor-0.10.2"
if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot "pyproject.toml") -PathType Leaf)) {
    throw "The canonical source root was not found after extraction."
}
$ProjectMetadata = Get-Content -LiteralPath (Join-Path $SourceRoot "pyproject.toml") -Raw
if ($ProjectMetadata -notmatch '(?m)^version = "0\.10\.2"$') {
    throw "The source archive does not identify itself as Relic Auditor 0.10.2."
}

$Launcher = Get-PythonLauncher
$VenvRoot = Join-Path $SafeBuildRoot "venv"
Invoke-Checked -Command $Launcher.Command -Arguments @($Launcher.Prefix + @("-m", "venv", $VenvRoot))
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
Invoke-Checked -Command $VenvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip", "setuptools", "wheel")
Invoke-Checked -Command $VenvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $InstallerRoot "requirements-build.txt"))
Invoke-Checked -Command $VenvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "$SourceRoot[all]")
Invoke-Checked -Command $VenvPython -Arguments @("-m", "pytest", "-q", (Join-Path $KitRoot "tests"))

Invoke-Checked -Command $VenvPython -Arguments @("-m", "pytest", "-q", (Join-Path $SourceRoot "tests"))
$VersionOutput = (& $VenvPython "-m" "relic_auditor" "--version" 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $VersionOutput -ne "relic 0.10.2") {
    throw "Unexpected source version output: $VersionOutput"
}

$env:RELIC_INSTALLER_ROOT = $InstallerRoot
$env:RELIC_BUILD_ROOT = $SafeBuildRoot
$env:RELIC_SOURCE_ROOT = $SourceRoot
$env:RELIC_INSTALLER_OUTPUT = $OutputDirectory
$PyInstallerDist = Join-Path $SafeBuildRoot "pyinstaller-dist"
$PyInstallerWork = Join-Path $SafeBuildRoot "pyinstaller-work"
$PyInstallerArguments = @(
    "-m", "PyInstaller", "--noconfirm", "--clean",
    "--distpath", $PyInstallerDist,
    "--workpath", $PyInstallerWork,
    (Join-Path $InstallerRoot "relic-auditor.spec")
)
Invoke-Checked -Command $VenvPython -Arguments $PyInstallerArguments

$GuiExe = Join-Path $PyInstallerDist "Relic Auditor\Relic Auditor.exe"
$CliExe = Join-Path $PyInstallerDist "relic-cli\relic.exe"
foreach ($ExpectedExecutable in @($GuiExe, $CliExe)) {
    if (-not (Test-Path -LiteralPath $ExpectedExecutable -PathType Leaf)) {
        throw "PyInstaller did not produce $ExpectedExecutable"
    }
    Sign-File $ExpectedExecutable
}

$BundledVersion = (& $CliExe "--version" 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $BundledVersion -ne "relic 0.10.2") {
    throw "Bundled CLI version verification failed: $BundledVersion"
}
$Fixture = Join-Path $SourceRoot "tests\fixtures\false_compliance"
$BundleSmokeRoot = Join-Path $SafeBuildRoot "bundle-smoke"
New-Item -ItemType Directory -Path $BundleSmokeRoot | Out-Null
Invoke-Checked -Command $CliExe -Arguments @("audit", $Fixture, "--output", (Join-Path $BundleSmokeRoot "audit"), "--technical-truth")
Invoke-Checked -Command $CliExe -Arguments @("acquire", $Fixture, "--output", (Join-Path $BundleSmokeRoot "acquire"))
$GuiSmoke = Start-Process -FilePath $GuiExe -ArgumentList "--smoke-test" -PassThru -Wait
if ($GuiSmoke.ExitCode -ne 0) {
    throw "Bundled Evidence Console smoke test failed with exit code $($GuiSmoke.ExitCode)."
}

$Compiler = Find-InnoSetup $InnoSetupPath
Invoke-Checked -Command $Compiler -Arguments @("/Qp", (Join-Path $InstallerRoot "relic-auditor.iss"))
$InstallerExe = Join-Path $OutputDirectory "Relic-Auditor-Setup-0.10.2-x64.exe"
if (-not (Test-Path -LiteralPath $InstallerExe -PathType Leaf)) {
    throw "Inno Setup did not produce the expected installer."
}
Sign-File $InstallerExe

$CleanInstall = Join-Path $SafeBuildRoot "clean-install"
$ConfigRoot = Join-Path $env:APPDATA "Relic Auditor"
New-Item -ItemType Directory -Path $ConfigRoot -Force | Out-Null
$Sentinel = Join-Path $ConfigRoot ("installer-preservation-" + [Guid]::NewGuid().ToString("N") + ".txt")
Set-Content -LiteralPath $Sentinel -Value "Relic user configuration must survive uninstall." -Encoding UTF8

try {
    $InstallProcess = Start-Process -FilePath $InstallerExe -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS=addtopath", "/DIR=`"$CleanInstall`""
    ) -PassThru -Wait
    if ($InstallProcess.ExitCode -ne 0) {
        throw "Silent installer verification failed with exit code $($InstallProcess.ExitCode)."
    }
    $InstalledCli = Join-Path $CleanInstall "cli\relic.exe"
    $InstalledGui = Join-Path $CleanInstall "Relic Auditor.exe"
    $InstalledVersion = (& $InstalledCli "--version" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $InstalledVersion -ne "relic 0.10.2") {
        throw "Installed CLI version verification failed: $InstalledVersion"
    }
    $InstallSmokeRoot = Join-Path $SafeBuildRoot "installed-smoke"
    New-Item -ItemType Directory -Path $InstallSmokeRoot | Out-Null
    Invoke-Checked -Command $InstalledCli -Arguments @("audit", $Fixture, "--output", (Join-Path $InstallSmokeRoot "audit"), "--technical-truth")
    Invoke-Checked -Command $InstalledCli -Arguments @("acquire", $Fixture, "--output", (Join-Path $InstallSmokeRoot "acquire"))
    $InstalledGuiSmoke = Start-Process -FilePath $InstalledGui -ArgumentList "--smoke-test" -PassThru -Wait
    if ($InstalledGuiSmoke.ExitCode -ne 0) {
        throw "Installed Evidence Console smoke test failed with exit code $($InstalledGuiSmoke.ExitCode)."
    }
    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($UserPath -split ';' | ForEach-Object { $_.Trim('"').TrimEnd('\') }) -notcontains ((Join-Path $CleanInstall "cli").TrimEnd('\'))) {
        throw "The installer did not register the selected CLI PATH entry."
    }
    if (-not (Test-Path -LiteralPath $Sentinel -PathType Leaf)) {
        throw "The installer altered pre-existing Relic user configuration."
    }

    $ObsoleteGuiRuntime = Join-Path $CleanInstall "_internal\obsolete-runtime.dll"
    $ObsoleteCliRuntime = Join-Path $CleanInstall "cli\_internal\obsolete-runtime.dll"
    Set-Content -LiteralPath $ObsoleteGuiRuntime -Value "stale GUI runtime" -Encoding ASCII
    Set-Content -LiteralPath $ObsoleteCliRuntime -Value "stale CLI runtime" -Encoding ASCII
    $UpgradeProcess = Start-Process -FilePath $InstallerExe -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS=addtopath", "/DIR=`"$CleanInstall`""
    ) -PassThru -Wait
    if ($UpgradeProcess.ExitCode -ne 0) {
        throw "In-place upgrade verification failed with exit code $($UpgradeProcess.ExitCode)."
    }
    if ((Test-Path -LiteralPath $ObsoleteGuiRuntime) -or (Test-Path -LiteralPath $ObsoleteCliRuntime)) {
        throw "The in-place upgrade left obsolete managed runtime files behind."
    }
    if (-not (Test-Path -LiteralPath $Sentinel -PathType Leaf)) {
        throw "The in-place upgrade altered Relic user configuration."
    }
    $UpgradedVersion = (& $InstalledCli "--version" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $UpgradedVersion -ne "relic 0.10.2") {
        throw "In-place upgrade version verification failed: $UpgradedVersion"
    }

    $Uninstaller = Join-Path $CleanInstall "unins000.exe"
    $UninstallProcess = Start-Process -FilePath $Uninstaller -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
    ) -PassThru -Wait
    if ($UninstallProcess.ExitCode -ne 0) {
        throw "Silent uninstall verification failed with exit code $($UninstallProcess.ExitCode)."
    }
    if (Test-Path -LiteralPath $InstalledGui -PathType Leaf) {
        throw "The uninstaller left the installed application executable behind."
    }
    if (-not (Test-Path -LiteralPath $Sentinel -PathType Leaf)) {
        throw "The uninstaller deleted Relic user configuration."
    }
    $UserPathAfter = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($UserPathAfter -split ';' | ForEach-Object { $_.Trim('"').TrimEnd('\') }) -contains ((Join-Path $CleanInstall "cli").TrimEnd('\'))) {
        throw "The uninstaller left its CLI PATH entry behind."
    }
}
finally {
    if (Test-Path -LiteralPath $Sentinel -PathType Leaf) {
        Remove-Item -LiteralPath $Sentinel -Force
    }
}

$InstallerHash = (Get-FileHash -LiteralPath $InstallerExe -Algorithm SHA256).Hash.ToLowerInvariant()
$InstallerSize = (Get-Item -LiteralPath $InstallerExe).Length
$Signature = Get-AuthenticodeSignature -LiteralPath $InstallerExe
$Manifest = [ordered]@{
    product = "Relic Auditor"
    version = "0.10.2"
    architecture = "x64"
    minimum_windows_build = "10.0.17763"
    source_archive = (Split-Path -Leaf $SourceArchive)
    source_sha256 = $ActualSourceHash
    installer = (Split-Path -Leaf $InstallerExe)
    installer_sha256 = $InstallerHash
    installer_size_bytes = $InstallerSize
    authenticode_status = $Signature.Status.ToString()
    python_bundled = $true
    python_required_on_target = $false
    source_tests_run = $true
    source_test_exclusions = @()
    source_test_exclusion_reason = ""
    bundled_cli_smoke = "passed"
    bundled_gui_smoke = "passed"
    clean_install_smoke = "passed"
    in_place_upgrade_smoke = "passed"
    stale_runtime_cleanup = "passed"
    uninstall_preserved_user_config = $true
    cli_path_cleanup = "passed"
    update_manifest_url = "https://relic-auditor.briandrichter.chatgpt.site/downloads/stable.json"
    updater_requires_trusted_authenticode = $true
    pyinstaller = "6.21.0"
}
$Manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDirectory "release-manifest.json") -Encoding UTF8
"$InstallerHash  $(Split-Path -Leaf $InstallerExe)" | Set-Content -LiteralPath (Join-Path $OutputDirectory "SHA256SUMS.txt") -Encoding ASCII
Copy-Item -LiteralPath (Join-Path $InstallerRoot "INSTALLER-README.md") -Destination (Join-Path $OutputDirectory "INSTALLER-README.md") -Force

Write-Host "Windows installer complete: $InstallerExe"
Write-Host "SHA-256: $InstallerHash"
Write-Host "Size: $InstallerSize bytes"
Write-Host "Authenticode: $($Signature.Status)"

if (-not $KeepBuildDirectory) {
    Remove-Item -LiteralPath $SafeBuildRoot -Recurse -Force
}
