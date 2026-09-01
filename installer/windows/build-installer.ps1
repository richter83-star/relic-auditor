#Requires -Version 7.2

[CmdletBinding()]
param(
    [string]$SourceArchive = "",
    [string]$ExpectedSourceSha256 = "",
    [string]$SourceCommit = "",
    [string]$OutputDirectory = "",
    [string]$InnoSetupPath = "",
    [string]$SigningCertificate = "",
    [string]$SigningPassword = "",
    [string]$PriorStableInstallerUrl = "https://github.com/richter83-star/relic-auditor/releases/download/v1.0.1/Relic-Auditor-Setup-1.0.1-x64.exe",
    [string]$ExpectedPriorStableInstallerSha256 = "56c3e20c9cdcf8e2a6beae76b0e05d928e1af0002e92240c83d1ace773069d10",
    [switch]$KeepBuildDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$InstallerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$KitRoot = (Resolve-Path (Join-Path $InstallerRoot "..\..")).Path
if (-not $SourceArchive) {
    $SourceArchive = Join-Path $KitRoot "releases\relic-auditor-1.0.2.zip"
}
if (-not $ExpectedSourceSha256) {
    throw "ExpectedSourceSha256 is required so the installer is built only from an explicitly verified frozen source archive."
}
if ($SourceCommit -notmatch '^[0-9a-fA-F]{40}$') {
    throw "SourceCommit is required and must be the exact 40-character commit SHA used to create the source archive."
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

function Assert-EntitlementGate {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$CapabilityName
    )
    $Output = (& $Command @Arguments 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 2 -or $Output -notmatch "requires a higher Relic entitlement") {
        throw "$CapabilityName entitlement-gate smoke failed. Exit code: $LASTEXITCODE. Output: $Output"
    }
}

function Get-ReadOnlyTreeDigest {
    param([Parameter(Mandatory = $true)][string]$Root)
    $ResolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    $Records = @("root|.")
    foreach ($Item in Get-ChildItem -LiteralPath $ResolvedRoot -Force -Recurse | Sort-Object FullName) {
        $Relative = [System.IO.Path]::GetRelativePath($ResolvedRoot, $Item.FullName).Replace('\', '/')
        if ($Item.PSIsContainer) {
            $Records += "directory|$Relative"
        }
        else {
            $Hash = (Get-FileHash -LiteralPath $Item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $Records += "file|$Relative|$($Item.Length)|$Hash"
        }
    }
    $Bytes = [System.Text.Encoding]::UTF8.GetBytes(($Records -join "`n"))
    return [Convert]::ToHexString(
        [System.Security.Cryptography.SHA256]::HashData($Bytes)
    ).ToLowerInvariant()
}

function Assert-ReadOnlyCliSequence {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$Fixture,
        [Parameter(Mandatory = $true)][string]$OutputRoot,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $Before = Get-ReadOnlyTreeDigest -Root $Fixture
    Invoke-Checked -Command $Command -Arguments @("audit", $Fixture, "--output", (Join-Path $OutputRoot "audit"), "--technical-truth") |
        ForEach-Object { Write-Host $_ }
    Invoke-Checked -Command $Command -Arguments @("acquire", $Fixture, "--output", (Join-Path $OutputRoot "acquire")) |
        ForEach-Object { Write-Host $_ }
    Invoke-Checked -Command $Command -Arguments @("resurrect", $Fixture, "--output", (Join-Path $OutputRoot "resurrection")) |
        ForEach-Object { Write-Host $_ }
    $After = Get-ReadOnlyTreeDigest -Root $Fixture
    if ($After -ne $Before) {
        throw "$Label modified the scan fixture. Before: $Before. After: $After."
    }
    Write-Host "$Label read-only target digest: $After"
    return $After
}

function Invoke-PytestEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$Python,
        [Parameter(Mandatory = $true)][string]$TestPath,
        [Parameter(Mandatory = $true)][string]$ResultPath
    )
    Invoke-Checked -Command $Python -Arguments @(
        "-m", "pytest", "-q", $TestPath, "--junitxml=$ResultPath"
    ) | ForEach-Object { Write-Host $_ }
    [xml]$Results = Get-Content -LiteralPath $ResultPath -Raw
    $Suites = @($Results.SelectNodes('/testsuites/testsuite | /testsuite'))
    if ($Suites.Count -eq 0) {
        throw "Pytest did not produce a top-level JUnit test suite in $ResultPath."
    }
    $Tests = [int](($Suites | Measure-Object -Property tests -Sum).Sum)
    $Failures = [int](($Suites | Measure-Object -Property failures -Sum).Sum)
    $Errors = [int](($Suites | Measure-Object -Property errors -Sum).Sum)
    $Skipped = [int](($Suites | Measure-Object -Property skipped -Sum).Sum)
    return [pscustomobject]@{
        total = $Tests
        passed = $Tests - $Failures - $Errors - $Skipped
        failed = $Failures
        errors = $Errors
        skipped = $Skipped
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
    throw "Relic Auditor 1.0.2 supports 64-bit Windows only."
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
        "Relic-Auditor-Setup-1.0.2-x64.exe",
        "SHA256SUMS.txt",
        "release-manifest.json",
        "INSTALLER-README.md",
        "checkout-tests.xml",
        "frozen-source-tests.xml"
    ) } |
    Remove-Item -Force

$UnpackedRoot = Join-Path $SafeBuildRoot "source-unpacked"
Expand-Archive -LiteralPath $SourceArchive -DestinationPath $UnpackedRoot -Force
$SourceRoot = Join-Path $UnpackedRoot "relic-auditor-1.0.2"
if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot "pyproject.toml") -PathType Leaf)) {
    throw "The canonical source root was not found after extraction."
}
$ProjectMetadata = Get-Content -LiteralPath (Join-Path $SourceRoot "pyproject.toml") -Raw
$ProjectVersionLines = $ProjectMetadata -split '\r?\n'
if ($ProjectVersionLines -notcontains 'version = "1.0.2"') {
    throw "The source archive does not identify itself as Relic Auditor 1.0.2."
}

$Launcher = Get-PythonLauncher
$VenvRoot = Join-Path $SafeBuildRoot "venv"
Invoke-Checked -Command $Launcher.Command -Arguments @($Launcher.Prefix + @("-m", "venv", $VenvRoot))
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
Invoke-Checked -Command $VenvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip", "setuptools", "wheel")
Invoke-Checked -Command $VenvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $InstallerRoot "requirements-build.txt"))
Invoke-Checked -Command $VenvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "$SourceRoot[all]")
$CheckoutTestEvidence = Invoke-PytestEvidence `
    -Python $VenvPython `
    -TestPath (Join-Path $KitRoot "tests") `
    -ResultPath (Join-Path $SafeBuildRoot "checkout-tests.xml")
$FrozenSourceTestEvidence = Invoke-PytestEvidence `
    -Python $VenvPython `
    -TestPath (Join-Path $SourceRoot "tests") `
    -ResultPath (Join-Path $SafeBuildRoot "frozen-source-tests.xml")
if (
    $CheckoutTestEvidence.passed -ne $FrozenSourceTestEvidence.passed -or
    $CheckoutTestEvidence.skipped -ne $FrozenSourceTestEvidence.skipped -or
    $CheckoutTestEvidence.failed -ne $FrozenSourceTestEvidence.failed -or
    $CheckoutTestEvidence.errors -ne $FrozenSourceTestEvidence.errors
) {
    throw "Checked-out and frozen-source test evidence do not match."
}
Write-Host (
    "Frozen source tests: {0} passed, {1} skipped, {2} failed, {3} errors" -f
    $FrozenSourceTestEvidence.passed,
    $FrozenSourceTestEvidence.skipped,
    $FrozenSourceTestEvidence.failed,
    $FrozenSourceTestEvidence.errors
)
$VersionOutput = (& $VenvPython "-m" "relic_auditor" "--version" 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $VersionOutput -ne "relic 1.0.2") {
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
if ($LASTEXITCODE -ne 0 -or $BundledVersion -ne "relic 1.0.2") {
    throw "Bundled CLI version verification failed: $BundledVersion"
}
Invoke-Checked -Command $CliExe -Arguments @("build-pack", "--help")
Invoke-Checked -Command $CliExe -Arguments @("build", "--help")
Assert-EntitlementGate -Command $CliExe -Arguments @(
    "build-pack", "list", (Join-Path $SafeBuildRoot "missing-opportunities.json"), "--json"
) -CapabilityName "Bundled Build Pack"
Assert-EntitlementGate -Command $CliExe -Arguments @(
    "build", "start", (Join-Path $SafeBuildRoot "missing-build-pack"),
    "--sessions", (Join-Path $SafeBuildRoot "missing-sessions"), "--json"
) -CapabilityName "Bundled Assisted Build"
$Fixture = Join-Path $SourceRoot "tests\fixtures\false_compliance"
$BundleSmokeRoot = Join-Path $SafeBuildRoot "bundle-smoke"
New-Item -ItemType Directory -Path $BundleSmokeRoot | Out-Null
$BundledReadOnlyDigest = Assert-ReadOnlyCliSequence `
    -Command $CliExe -Fixture $Fixture -OutputRoot $BundleSmokeRoot -Label "Bundled CLI"
$GuiSmoke = Start-Process -FilePath $GuiExe -ArgumentList "--smoke-test" -PassThru -Wait
if ($GuiSmoke.ExitCode -ne 0) {
    throw "Bundled Evidence Console smoke test failed with exit code $($GuiSmoke.ExitCode)."
}

$Compiler = Find-InnoSetup $InnoSetupPath
Invoke-Checked -Command $Compiler -Arguments @("/Qp", (Join-Path $InstallerRoot "relic-auditor.iss"))
$InstallerExe = Join-Path $OutputDirectory "Relic-Auditor-Setup-1.0.2-x64.exe"
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
    if ($LASTEXITCODE -ne 0 -or $InstalledVersion -ne "relic 1.0.2") {
        throw "Installed CLI version verification failed: $InstalledVersion"
    }
    Invoke-Checked -Command $InstalledCli -Arguments @("build-pack", "--help")
    Invoke-Checked -Command $InstalledCli -Arguments @("build", "--help")
    Assert-EntitlementGate -Command $InstalledCli -Arguments @(
        "build-pack", "list", (Join-Path $SafeBuildRoot "missing-installed-opportunities.json"), "--json"
    ) -CapabilityName "Installed Build Pack"
    Assert-EntitlementGate -Command $InstalledCli -Arguments @(
        "build", "start", (Join-Path $SafeBuildRoot "missing-installed-build-pack"),
        "--sessions", (Join-Path $SafeBuildRoot "missing-installed-sessions"), "--json"
    ) -CapabilityName "Installed Assisted Build"
    $InstallSmokeRoot = Join-Path $SafeBuildRoot "installed-smoke"
    New-Item -ItemType Directory -Path $InstallSmokeRoot | Out-Null
    $InstalledReadOnlyDigest = Assert-ReadOnlyCliSequence `
        -Command $InstalledCli -Fixture $Fixture -OutputRoot $InstallSmokeRoot -Label "Installed CLI"
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
    if ($LASTEXITCODE -ne 0 -or $UpgradedVersion -ne "relic 1.0.2") {
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

$PriorStableInstaller = Join-Path $SafeBuildRoot "Relic-Auditor-Setup-1.0.1-x64.exe"
Invoke-WebRequest -Uri $PriorStableInstallerUrl -OutFile $PriorStableInstaller -UseBasicParsing
$PriorStableHash = (Get-FileHash -LiteralPath $PriorStableInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
if ($PriorStableHash -ne $ExpectedPriorStableInstallerSha256.ToLowerInvariant()) {
    throw "Prior stable installer hash mismatch. Expected $ExpectedPriorStableInstallerSha256 but found $PriorStableHash."
}

$StableUpgradeInstall = Join-Path $SafeBuildRoot "stable-upgrade"
$UpgradeSentinel = Join-Path $ConfigRoot ("stable-upgrade-preservation-" + [Guid]::NewGuid().ToString("N") + ".txt")
Set-Content -LiteralPath $UpgradeSentinel -Value "Relic user configuration must survive a stable-version upgrade." -Encoding UTF8
try {
    $StableInstallProcess = Start-Process -FilePath $PriorStableInstaller -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=`"$StableUpgradeInstall`""
    ) -PassThru -Wait
    if ($StableInstallProcess.ExitCode -ne 0) {
        throw "Stable v1.0.1 installation failed with exit code $($StableInstallProcess.ExitCode)."
    }
    $StableCli = Join-Path $StableUpgradeInstall "cli\relic.exe"
    $StableVersion = (& $StableCli "--version" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $StableVersion -ne "relic 1.0.1") {
        throw "Expected stable v1.0.1 before upgrade, found: $StableVersion"
    }

    $StableUpgradeProcess = Start-Process -FilePath $InstallerExe -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=`"$StableUpgradeInstall`""
    ) -PassThru -Wait
    if ($StableUpgradeProcess.ExitCode -ne 0) {
        throw "v1.0.1 to v1.0.2 upgrade failed with exit code $($StableUpgradeProcess.ExitCode)."
    }
    $UpgradedStableVersion = (& $StableCli "--version" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $UpgradedStableVersion -ne "relic 1.0.2") {
        throw "Expected v1.0.2 after stable upgrade, found: $UpgradedStableVersion"
    }
    if (-not (Test-Path -LiteralPath $UpgradeSentinel -PathType Leaf)) {
        throw "The v1.0.1 to v1.0.2 upgrade altered Relic user configuration."
    }

    $StableUninstaller = Join-Path $StableUpgradeInstall "unins000.exe"
    $StableUninstallProcess = Start-Process -FilePath $StableUninstaller -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
    ) -PassThru -Wait
    if ($StableUninstallProcess.ExitCode -ne 0) {
        throw "Upgraded installation uninstall failed with exit code $($StableUninstallProcess.ExitCode)."
    }
    if (Test-Path -LiteralPath (Join-Path $StableUpgradeInstall "Relic Auditor.exe") -PathType Leaf) {
        throw "The upgraded installation uninstaller left the application executable behind."
    }
    if (-not (Test-Path -LiteralPath $UpgradeSentinel -PathType Leaf)) {
        throw "Uninstall after stable upgrade deleted Relic user configuration."
    }
}
finally {
    if (Test-Path -LiteralPath $UpgradeSentinel -PathType Leaf) {
        Remove-Item -LiteralPath $UpgradeSentinel -Force
    }
}

$InstallerHash = (Get-FileHash -LiteralPath $InstallerExe -Algorithm SHA256).Hash.ToLowerInvariant()
$InstallerSize = (Get-Item -LiteralPath $InstallerExe).Length
$Signature = Get-AuthenticodeSignature -LiteralPath $InstallerExe
$Manifest = [ordered]@{
    product = "Relic Auditor"
    version = "1.0.2"
    source_commit = $SourceCommit.ToLowerInvariant()
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
    source_tests_total = $FrozenSourceTestEvidence.total
    source_tests_passed = $FrozenSourceTestEvidence.passed
    source_tests_skipped = $FrozenSourceTestEvidence.skipped
    source_tests_failed = $FrozenSourceTestEvidence.failed
    source_tests_errors = $FrozenSourceTestEvidence.errors
    source_test_exclusions = @()
    source_test_exclusion_reason = ""
    bundled_cli_smoke = "passed"
    bundled_gui_smoke = "passed"
    bundled_resurrection_smoke = "passed"
    bundled_build_pack_entitlement_gate_smoke = "passed"
    bundled_assisted_build_entitlement_gate_smoke = "passed"
    clean_install_smoke = "passed"
    installed_resurrection_smoke = "passed"
    bundled_read_only_target_digest = $BundledReadOnlyDigest
    installed_read_only_target_digest = $InstalledReadOnlyDigest
    installed_build_pack_entitlement_gate_smoke = "passed"
    installed_assisted_build_entitlement_gate_smoke = "passed"
    in_place_upgrade_smoke = "passed_same_version_reinstall"
    same_version_repair_smoke = "passed"
    stable_upgrade_from = "1.0.1"
    stable_upgrade_installer_sha256 = $PriorStableHash
    stable_upgrade_smoke = "passed"
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
Copy-Item -LiteralPath (Join-Path $SafeBuildRoot "checkout-tests.xml") -Destination (Join-Path $OutputDirectory "checkout-tests.xml") -Force
Copy-Item -LiteralPath (Join-Path $SafeBuildRoot "frozen-source-tests.xml") -Destination (Join-Path $OutputDirectory "frozen-source-tests.xml") -Force

Write-Host "Windows installer complete: $InstallerExe"
Write-Host "SHA-256: $InstallerHash"
Write-Host "Size: $InstallerSize bytes"
Write-Host "Authenticode: $($Signature.Status)"

if (-not $KeepBuildDirectory) {
    Remove-Item -LiteralPath $SafeBuildRoot -Recurse -Force
}
