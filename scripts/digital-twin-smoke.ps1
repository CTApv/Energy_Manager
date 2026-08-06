param(
    [string]$ApiBase = "http://localhost:8000/api",
    [string]$Username = "admin",
    [string]$Password = "EnergyDemo!2026",
    [string]$AccessToken = "",
    [switch]$RequireQualification
)

$ErrorActionPreference = "Stop"

function Invoke-LabApi {
    param([string]$Method, [string]$Path, [object]$Body)
    $arguments = @{
        Method = $Method
        Uri = "$ApiBase$Path"
        Headers = @{ Authorization = "Bearer $script:AccessToken" }
        ContentType = "application/json"
    }
    if ($null -ne $Body) { $arguments.Body = ($Body | ConvertTo-Json -Depth 8) }
    Invoke-RestMethod @arguments
}

if ($AccessToken) {
    $script:AccessToken = $AccessToken
} else {
    $session = Invoke-RestMethod -Method Post -Uri "$ApiBase/auth/token" -ContentType "application/x-www-form-urlencoded" -Body @{
        username = $Username
        password = $Password
    }
    $script:AccessToken = $session.access_token
}

$status = Invoke-LabApi Get "/digital-twin/status" $null
if (-not $status.healthy) { throw "Simulator fleet is not healthy ($($status.reachable)/$($status.total))" }

$scenario = Invoke-LabApi Post "/digital-twin/scenario" @{
    scenario = "evening_peak"
    time_scale = 120
    virtual_time = "2026-06-21T19:30:00Z"
}
if ([math]::Abs([double]$scenario.status.balance_error_kw) -ge 0.01) { throw "Energy balance check failed" }

$fault = Invoke-LabApi Post "/digital-twin/fault" @{
    name = "identical_registers"
    enabled = $true
    value = $true
    profiles = @("meter")
}
if (-not $fault.status.faults.identical_registers) { throw "Fault injection was not acknowledged" }

Invoke-LabApi Post "/digital-twin/faults/clear" @{} | Out-Null
$stress = Invoke-LabApi Post "/digital-twin/stress" @{
    units = 100
    cycles = 2
    mode = "shared_gateway"
    max_connections = 8
    timeout_seconds = 2
}
if (-not $stress.result.passed) { throw "Stress test failed: $($stress.result | ConvertTo-Json -Compress)" }

$qualification = Invoke-LabApi Post "/digital-twin/qualification" @{}
[pscustomobject]@{
    Scenario = $scenario.status.scenario
    Services = "$($scenario.status.reachable)/$($scenario.status.total)"
    StressRequests = $stress.result.requests_ok
    StressP95Ms = $stress.result.latency_ms.p95
    QualificationScore = $qualification.result.score
    QualificationPassed = $qualification.result.passed
} | Format-List

if ($RequireQualification -and -not $qualification.result.passed) { throw "Qualification checklist did not pass" }
