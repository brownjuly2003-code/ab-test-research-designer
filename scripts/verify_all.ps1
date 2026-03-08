param(
  [switch]$SkipSmoke,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
  param(
    [string]$Label,
    [scriptblock]$Action
  )

  Write-Host "[verify] $Label"
  & $Action
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}

$root = Split-Path -Parent $PSScriptRoot

Push-Location $root
try {
  Invoke-Step "generated api contracts" { python scripts/generate_frontend_api_types.py --check }
  Invoke-Step "backend tests" { python -m pytest app/backend/tests -q }

  Push-Location (Join-Path $root "app/frontend")
  try {
    Invoke-Step "frontend typecheck" { npm.cmd exec tsc -- --noEmit -p . }
    Invoke-Step "frontend unit tests" { npm.cmd run test:unit }

    if (-not $SkipBuild) {
      Invoke-Step "frontend build" { npm.cmd run build }
    }
  }
  finally {
    Pop-Location
  }

  if (-not $SkipSmoke) {
    if ($SkipBuild) {
      Invoke-Step "local smoke" { python scripts/run_local_smoke.py --skip-build }
    }
    else {
      Invoke-Step "local smoke" { python scripts/run_local_smoke.py --skip-build }
    }
  }

  Write-Host "[verify] all checks passed"
}
finally {
  Pop-Location
}
