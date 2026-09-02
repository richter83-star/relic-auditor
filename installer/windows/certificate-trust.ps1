#Requires -Version 7.2

function Assert-TrustedCertificateChain {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [Parameter(Mandatory = $true)][string]$ApplicationPolicyOid,
        [Parameter(Mandatory = $true)][string]$CertificatePurpose
    )

    $Chain = [System.Security.Cryptography.X509Certificates.X509Chain]::new()
    try {
        $Chain.ChainPolicy.RevocationMode = `
            [System.Security.Cryptography.X509Certificates.X509RevocationMode]::Online
        $Chain.ChainPolicy.RevocationFlag = `
            [System.Security.Cryptography.X509Certificates.X509RevocationFlag]::ExcludeRoot
        $Chain.ChainPolicy.VerificationFlags = `
            [System.Security.Cryptography.X509Certificates.X509VerificationFlags]::NoFlag
        $Chain.ChainPolicy.UrlRetrievalTimeout = [TimeSpan]::FromSeconds(30)
        [void]$Chain.ChainPolicy.ApplicationPolicy.Add(
            [System.Security.Cryptography.Oid]::new($ApplicationPolicyOid)
        )

        if (-not $Chain.Build($Certificate)) {
            $Statuses = @(
                foreach ($Status in $Chain.ChainStatus) {
                    "$($Status.Status): $($Status.StatusInformation.Trim())"
                }
            ) -join "; "
            if ([string]::IsNullOrWhiteSpace($Statuses)) {
                $Statuses = "unknown chain validation failure"
            }
            throw "The $CertificatePurpose certificate does not chain to a trusted root. Chain status: $Statuses"
        }
    }
    finally {
        $Chain.Dispose()
    }
}
