param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$')][string]$Hostname,
    [string]$OutputPath = ".env"
)

if (Test-Path -LiteralPath $OutputPath) {
    throw "Il file $OutputPath esiste già. Non verrà sovrascritto."
}

function New-HexSecret([int]$Bytes = 48) {
    $buffer = New-Object byte[] $Bytes
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [Convert]::ToHexString($buffer).ToLowerInvariant()
}

$databasePassword = New-HexSecret 32
$content = @"
EM_CONTROL_ROOM_HOSTNAME=$Hostname
POSTGRES_PASSWORD=$databasePassword
EM_CONTROL_DATABASE_URL=postgresql+psycopg://energy:$databasePassword@control-db:5432/energy_manager
EM_SECRET_KEY=$(New-HexSecret)
EM_BOOTSTRAP_ADMIN_PASSWORD=$(New-HexSecret 24)
EM_EDGE_TOKEN=$(New-HexSecret)
EM_WEBHOOK_SECRET=$(New-HexSecret)
EM_CONTROL_RAW_RETENTION_DAYS=30
EM_ROLLUP_RETENTION_DAYS=3650
"@

Set-Content -LiteralPath $OutputPath -Value $content -Encoding utf8 -NoNewline
Write-Host "Creato $OutputPath. Conservarlo in un secret store e predisporre il backup PostgreSQL."
