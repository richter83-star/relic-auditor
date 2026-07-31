[CmdletBinding()]
param(
    [string]$PartsDirectory = (Join-Path $PSScriptRoot "Relic-Auditor-Setup-0.8.2-x64.exe.parts"),
    [string]$OutputPath = (Join-Path $PSScriptRoot "Relic-Auditor-Setup-0.8.2-x64.exe")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedSha256 = "0f1d1efe8375772d8ff23ad959cc96867174e7d0e4becded663933b09927daeb"
$Parts = @(
    Get-ChildItem -LiteralPath $PartsDirectory -Filter "part-*.part" -File |
        Sort-Object Name
)

if ($Parts.Count -ne 3) {
    throw "Expected exactly 3 installer parts, found $($Parts.Count)."
}
if (Test-Path -LiteralPath $OutputPath) {
    throw "Output already exists: $OutputPath"
}

$PartialPath = "$OutputPath.partial"
try {
    $Destination = [IO.File]::Open(
        $PartialPath,
        [IO.FileMode]::Create,
        [IO.FileAccess]::Write,
        [IO.FileShare]::None
    )
    try {
        foreach ($Part in $Parts) {
            $Input = [IO.File]::OpenRead($Part.FullName)
            try {
                $Input.CopyTo($Destination)
            }
            finally {
                $Input.Dispose()
            }
        }
    }
    finally {
        $Destination.Dispose()
    }

    $ActualSha256 = (
        Get-FileHash -LiteralPath $PartialPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        throw "Installer hash mismatch: $ActualSha256"
    }

    Move-Item -LiteralPath $PartialPath -Destination $OutputPath
    Write-Host "Verified installer created: $OutputPath"
    Write-Host "SHA-256: $ActualSha256"
}
finally {
    if (Test-Path -LiteralPath $PartialPath) {
        Remove-Item -LiteralPath $PartialPath -Force
    }
}
