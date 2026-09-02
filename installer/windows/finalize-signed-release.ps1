#Requires -Version 7.2

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$UnsignedReleaseDirectory,
    [Parameter(Mandatory = $true)][string]$SignedArtifactDirectory,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [Parameter(Mandatory = $true)][string]$ExpectedSourceCommit,
    [Parameter(Mandatory = $true)][string]$ExpectedPublisher,
    [Parameter(Mandatory = $true)][string]$SigningProvider
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ($ExpectedSourceCommit -notmatch '^[0-9a-fA-F]{40}$') {
    throw "ExpectedSourceCommit must be an exact 40-character commit SHA."
}
if ([string]::IsNullOrWhiteSpace($ExpectedPublisher)) {
    throw "ExpectedPublisher must match the publisher pinned by the updater."
}
if ([string]::IsNullOrWhiteSpace($SigningProvider)) {
    throw "SigningProvider is required for the release evidence."
}

$UnsignedRoot = (Resolve-Path -LiteralPath $UnsignedReleaseDirectory).Path
$SignedRoot = (Resolve-Path -LiteralPath $SignedArtifactDirectory).Path
$OutputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
if ($OutputRoot -eq $UnsignedRoot -or $OutputRoot -eq $SignedRoot) {
    throw "OutputDirectory must be separate from the unsigned and provider output directories."
}
if (Test-Path -LiteralPath $OutputRoot) {
    if (@(Get-ChildItem -LiteralPath $OutputRoot -Force).Count -ne 0) {
        throw "OutputDirectory must be empty so stale release files cannot survive finalization."
    }
}
else {
    New-Item -ItemType Directory -Path $OutputRoot | Out-Null
}

$ManifestPath = Join-Path $UnsignedRoot "release-manifest.json"
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "The unsigned release manifest is missing."
}
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$RequiredProperties = @(
    "product",
    "version",
    "source_commit",
    "source_archive",
    "source_sha256",
    "installer",
    "installer_sha256",
    "installer_size_bytes",
    "authenticode_status",
    "updater_requires_trusted_authenticode"
)
foreach ($Property in $RequiredProperties) {
    if ($Manifest.PSObject.Properties.Name -notcontains $Property) {
        throw "The unsigned release manifest is missing $Property."
    }
}

$ExpectedCommit = $ExpectedSourceCommit.ToLowerInvariant()
if ([string]$Manifest.source_commit -ne $ExpectedCommit) {
    throw "The unsigned release manifest does not match the authorized source commit."
}
if ([string]$Manifest.product -ne "Relic Auditor" -or [string]$Manifest.version -ne "1.0.3") {
    throw "The unsigned release manifest does not describe Relic Auditor 1.0.3."
}
if ([string]$Manifest.installer -ne "Relic-Auditor-Setup-1.0.3-x64.exe") {
    throw "The unsigned release manifest names an unexpected installer."
}
if ([string]$Manifest.source_archive -ne "relic-auditor-1.0.3.zip") {
    throw "The unsigned release manifest names an unexpected source archive."
}
if ([string]$Manifest.authenticode_status -ne "NotSigned") {
    throw "Managed signing accepts only the lifecycle-tested unsigned candidate."
}
if (-not [bool]$Manifest.updater_requires_trusted_authenticode) {
    throw "The release manifest must preserve the fail-closed Authenticode gate."
}

$UnsignedInstaller = Join-Path $UnsignedRoot ([string]$Manifest.installer)
if (-not (Test-Path -LiteralPath $UnsignedInstaller -PathType Leaf)) {
    throw "The lifecycle-tested unsigned installer is missing."
}
$UnsignedHash = (Get-FileHash -LiteralPath $UnsignedInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
$UnsignedSize = (Get-Item -LiteralPath $UnsignedInstaller).Length
if ($UnsignedHash -ne [string]$Manifest.installer_sha256 -or $UnsignedSize -ne [long]$Manifest.installer_size_bytes) {
    throw "The unsigned installer no longer matches its lifecycle-test manifest."
}

$SourceArchive = Join-Path $UnsignedRoot ([string]$Manifest.source_archive)
if (-not (Test-Path -LiteralPath $SourceArchive -PathType Leaf)) {
    throw "The frozen source archive is missing from the unsigned release evidence."
}
$SourceHash = (Get-FileHash -LiteralPath $SourceArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($SourceHash -ne [string]$Manifest.source_sha256) {
    throw "The frozen source archive no longer matches the release manifest."
}

$SignedMatches = @(
    Get-ChildItem -LiteralPath $SignedRoot -Recurse -File |
        Where-Object { $_.Name -eq [string]$Manifest.installer }
)
if ($SignedMatches.Count -ne 1) {
    throw "Expected exactly one provider-returned signed installer; found $($SignedMatches.Count)."
}
$SignedInstaller = $SignedMatches[0].FullName
$SignedHash = (Get-FileHash -LiteralPath $SignedInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
$SignedSize = (Get-Item -LiteralPath $SignedInstaller).Length
if ($SignedHash -eq $UnsignedHash) {
    throw "The provider-returned installer is byte-identical to the unsigned candidate."
}

$Signature = Get-AuthenticodeSignature -LiteralPath $SignedInstaller
if ($Signature.Status.ToString() -ne "Valid" -or $null -eq $Signature.SignerCertificate) {
    throw "The provider-returned installer does not have a valid Authenticode signature. Status: $($Signature.Status)."
}
$ActualPublisher = $Signature.SignerCertificate.GetNameInfo(
    [System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,
    $false
)
if ($ActualPublisher -cne $ExpectedPublisher) {
    throw "Authenticode publisher mismatch. Expected '$ExpectedPublisher' but found '$ActualPublisher'."
}
if ($null -eq $Signature.TimeStamperCertificate) {
    throw "The provider-returned installer is not Authenticode timestamped."
}

$SignedInstallRoot = Join-Path (
    [System.IO.Path]::GetTempPath()
) ("relic-signed-smoke-" + [Guid]::NewGuid().ToString("N"))
$SignedUninstaller = Join-Path $SignedInstallRoot "unins000.exe"
try {
    $InstallProcess = Start-Process -FilePath $SignedInstaller -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/MERGETASKS=!addtopath",
        "/DIR=`"$SignedInstallRoot`""
    ) -PassThru -Wait
    if ($InstallProcess.ExitCode -ne 0) {
        throw "The signed installer smoke install failed with exit code $($InstallProcess.ExitCode)."
    }
    $SignedCli = Join-Path $SignedInstallRoot "cli\relic.exe"
    $SignedGui = Join-Path $SignedInstallRoot "Relic Auditor.exe"
    $SignedVersion = (& $SignedCli "--version" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $SignedVersion -ne "relic 1.0.3") {
        throw "The signed installer produced an unexpected CLI version: $SignedVersion"
    }
    $GuiSmoke = Start-Process -FilePath $SignedGui -ArgumentList "--smoke-test" -PassThru -Wait
    if ($GuiSmoke.ExitCode -ne 0) {
        throw "The signed installer GUI smoke test failed with exit code $($GuiSmoke.ExitCode)."
    }
    if (-not (Test-Path -LiteralPath $SignedUninstaller -PathType Leaf)) {
        throw "The signed installer did not create the expected uninstaller."
    }
    $UninstallProcess = Start-Process -FilePath $SignedUninstaller -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
    ) -PassThru -Wait
    if ($UninstallProcess.ExitCode -ne 0) {
        throw "The signed installer smoke uninstall failed with exit code $($UninstallProcess.ExitCode)."
    }
    if (Test-Path -LiteralPath $SignedGui -PathType Leaf) {
        throw "The signed installer smoke uninstall left the application executable behind."
    }
}
finally {
    if (Test-Path -LiteralPath $SignedUninstaller -PathType Leaf) {
        Start-Process -FilePath $SignedUninstaller -ArgumentList @(
            "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
        ) -Wait -ErrorAction SilentlyContinue | Out-Null
    }
    if (Test-Path -LiteralPath $SignedInstallRoot) {
        Remove-Item -LiteralPath $SignedInstallRoot -Recurse -Force
    }
}

$EvidenceFiles = @(
    [string]$Manifest.source_archive,
    "INSTALLER-README.md",
    "checkout-tests.xml",
    "frozen-source-tests.xml"
)
foreach ($Name in $EvidenceFiles) {
    $Source = Join-Path $UnsignedRoot $Name
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Required release evidence is missing: $Name"
    }
    Copy-Item -LiteralPath $Source -Destination (Join-Path $OutputRoot $Name)
}
Copy-Item -LiteralPath $SignedInstaller -Destination (Join-Path $OutputRoot ([string]$Manifest.installer))

$Manifest.installer_sha256 = $SignedHash
$Manifest.installer_size_bytes = $SignedSize
$Manifest.authenticode_status = "Valid"
$Manifest | Add-Member -NotePropertyName "unsigned_installer_sha256" -NotePropertyValue $UnsignedHash
$Manifest | Add-Member -NotePropertyName "unsigned_installer_size_bytes" -NotePropertyValue $UnsignedSize
$Manifest | Add-Member -NotePropertyName "authenticode_publisher" -NotePropertyValue $ActualPublisher
$Manifest | Add-Member -NotePropertyName "authenticode_subject" -NotePropertyValue $Signature.SignerCertificate.Subject
$Manifest | Add-Member -NotePropertyName "authenticode_thumbprint" -NotePropertyValue $Signature.SignerCertificate.Thumbprint.ToLowerInvariant()
$Manifest | Add-Member -NotePropertyName "authenticode_timestamp_subject" -NotePropertyValue $Signature.TimeStamperCertificate.Subject
$Manifest | Add-Member -NotePropertyName "signing_provider" -NotePropertyValue $SigningProvider
$Manifest | Add-Member -NotePropertyName "signed_clean_install_smoke" -NotePropertyValue "passed"
$Manifest | Add-Member -NotePropertyName "signed_cli_smoke" -NotePropertyValue "passed"
$Manifest | Add-Member -NotePropertyName "signed_gui_smoke" -NotePropertyValue "passed"
$Manifest | Add-Member -NotePropertyName "signed_uninstall_smoke" -NotePropertyValue "passed"
$Manifest | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $OutputRoot "release-manifest.json") -Encoding UTF8
"$SignedHash  $($Manifest.installer)" |
    Set-Content -LiteralPath (Join-Path $OutputRoot "SHA256SUMS.txt") -Encoding ASCII

Write-Host "Signed release evidence finalized from source commit $ExpectedCommit."
Write-Host "Installer SHA-256: $SignedHash"
Write-Host "Installer size: $SignedSize bytes"
Write-Host "Authenticode publisher: $ActualPublisher"
Write-Host "Certificate thumbprint: $($Signature.SignerCertificate.Thumbprint.ToLowerInvariant())"
