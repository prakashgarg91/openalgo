# Starts OpenAlgo on Windows when an antivirus scans secure connections (Avast Web Shield and similar).
#
# Two things go wrong without this, and both are quiet:
#   1. Avast sets SSLKEYLOGFILE to one of its own devices. Python exits at once with "no OPENSSL_Applink".
#   2. The antivirus puts its own certificate on secure connections. Python does not know it, so the model
#      tests and the ChatGPT sign-in fail with "unable to get local issuer certificate".
# This clears the first and, only when the antivirus certificate is installed in Windows, adds it to a copy
# of Python's certificate list that applies to this one run. Nothing permanent is changed.
param([switch]$PrepareOnly)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repo

Remove-Item Env:SSLKEYLOGFILE -ErrorAction SilentlyContinue

$roots = @(Get-ChildItem Cert:\CurrentUser\Root, Cert:\LocalMachine\Root -ErrorAction SilentlyContinue |
    Where-Object { $_.Subject -match "Avast Web/Mail Shield Root|AVG Web/Mail Shield Root" })

if ($roots.Count -gt 0) {
    $certifi = (& uv run python -c "import certifi;print(certifi.where())").Trim()
    $bundle = Join-Path $env:USERPROFILE "openalgo-ca-bundle.pem"
    $text = Get-Content $certifi -Raw
    foreach ($root in ($roots | Select-Object -Unique Thumbprint, RawData -First 1)) {
        $text += "`n-----BEGIN CERTIFICATE-----`n" +
            [Convert]::ToBase64String($root.RawData, "InsertLineBreaks") +
            "`n-----END CERTIFICATE-----`n"
    }
    Set-Content -Path $bundle -Value $text -Encoding ascii
    $env:SSL_CERT_FILE = $bundle
    $env:REQUESTS_CA_BUNDLE = $bundle
    $env:CURL_CA_BUNDLE = $bundle
    Write-Host "Antivirus certificate found; using $bundle for this run."
} else {
    Write-Host "No antivirus scanning certificate found; using the normal certificate list."
}

if ($PrepareOnly) { Write-Host "Prepared only; the app was not started."; exit 0 }

& uv run app.py
exit $LASTEXITCODE
