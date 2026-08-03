param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$')][string]$Hostname,
    [string]$OutputPath = ".env"
)

if (Test-Path -LiteralPath $OutputPath) {
    throw "Il file $OutputPath esiste già. Non verrà sovrascritto."
}

function New-Secret([int]$Bytes = 48) {
    $buffer = New-Object byte[] $Bytes
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($buffer)
}

$content = @"
EM_EDGE_HOSTNAME=$Hostname
EM_SECRET_KEY=$(New-Secret)
EM_EDGE_TOKEN=$(New-Secret)
EM_WEBHOOK_SECRET=$(New-Secret)
EM_BOOTSTRAP_ADMIN_PASSWORD=$(New-Secret 24)
EM_SYNC_ENABLED=false
EM_CONTROL_ROOM_URL=https://control-room.invalid
EM_TELEMETRY_RETENTION_DAYS=730
EM_SENT_OUTBOX_RETENTION_DAYS=30
EM_BACKUP_ENABLED=true
EM_BACKUP_INTERVAL_HOURS=24
EM_BACKUP_RETENTION_COUNT=14
EM_RTU_DEVICE=/dev/ttyUSB0
"@

Set-Content -LiteralPath $OutputPath -Value $content -Encoding utf8 -NoNewline
Write-Host "Creato $OutputPath. Proteggerlo e non inviarlo via e-mail o chat."
