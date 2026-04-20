param(
  [switch]$SkipSmoke,
  [switch]$SkipBuild,
  [switch]$WithE2E,
  [switch]$WithDocker,
  [switch]$WithDockerPreserve
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$arguments = New-Object System.Collections.Generic.List[string]
$arguments.Add("/d")
$arguments.Add("/c")
$arguments.Add("scripts\verify_all.cmd")

if ($SkipSmoke) {
  $arguments.Add("--skip-smoke")
}
if ($SkipBuild) {
  $arguments.Add("--skip-build")
}
if ($WithE2E) {
  $arguments.Add("--with-e2e")
}
if ($WithDocker) {
  $arguments.Add("--with-docker")
}
if ($WithDockerPreserve) {
  $arguments.Add("--with-docker-preserve")
}
if ($WithDocker -and $WithDockerPreserve) {
  throw "--WithDocker and --WithDockerPreserve are mutually exclusive."
}

Push-Location $root
try {
  & cmd.exe @arguments
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}
finally {
  Pop-Location
}
