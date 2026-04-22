@echo off
setlocal

set "SKIP_SMOKE=0"
set "SKIP_BUILD=0"
set "WITH_E2E=0"
set "WITH_COVERAGE=0"
set "ARTIFACTS_DIR="
set "WITH_LIGHTHOUSE=0"
set "WITH_DOCKER=0"
set "WITH_DOCKER_PRESERVE=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--skip-smoke" set "SKIP_SMOKE=1"
if /I "%~1"=="--skip-build" set "SKIP_BUILD=1"
if /I "%~1"=="--with-e2e" set "WITH_E2E=1"
if /I "%~1"=="--with-coverage" set "WITH_COVERAGE=1"
if /I "%~1"=="--artifacts-dir" (
  set "ARTIFACTS_DIR=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--with-lighthouse" set "WITH_LIGHTHOUSE=1"
if /I "%~1"=="--with-docker" set "WITH_DOCKER=1"
if /I "%~1"=="--with-docker-preserve" set "WITH_DOCKER_PRESERVE=1"
shift
goto parse_args

:args_done
if "%WITH_DOCKER%"=="1" if "%WITH_DOCKER_PRESERVE%"=="1" (
  echo [verify] error: --with-docker and --with-docker-preserve are mutually exclusive
  exit /b 2
)
set "ROOT_DIR=%CD%\"
if not exist "%ROOT_DIR%scripts\generate_frontend_api_types.py" (
  for %%I in ("%~f0") do set "SCRIPT_DIR=%%~dpI"
  for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"
)
if not "%ARTIFACTS_DIR%"=="" (
  if not exist "%ARTIFACTS_DIR%" mkdir "%ARTIFACTS_DIR%"
  for %%I in ("%ARTIFACTS_DIR%") do set "ARTIFACTS_DIR=%%~fI"
)

echo [verify] generated api contracts
python "%ROOT_DIR%scripts\generate_frontend_api_types.py" --check
if errorlevel 1 exit /b %errorlevel%

echo [verify] generated api docs
python "%ROOT_DIR%scripts\generate_api_docs.py" --check
if errorlevel 1 exit /b %errorlevel%

set "ORIGINAL_AB_WORKSPACE_SIGNING_KEY=%AB_WORKSPACE_SIGNING_KEY%"
set "AB_WORKSPACE_SIGNING_KEY="
echo [verify] workspace backup roundtrip (checksum)
python "%ROOT_DIR%scripts\verify_workspace_backup.py" --fixture
if errorlevel 1 exit /b %errorlevel%
set "AB_WORKSPACE_SIGNING_KEY=verify-workspace-signing-key"
echo [verify] workspace backup roundtrip (signed)
python "%ROOT_DIR%scripts\verify_workspace_backup.py" --fixture
if errorlevel 1 exit /b %errorlevel%
set "AB_WORKSPACE_SIGNING_KEY=%ORIGINAL_AB_WORKSPACE_SIGNING_KEY%"

echo [verify] backend tests
set "BACKEND_JUNIT_PATH="
if not "%ARTIFACTS_DIR%"=="" set "BACKEND_JUNIT_PATH=%ARTIFACTS_DIR%\backend-junit.xml"
set "BACKEND_COVERAGE_PATH="
if "%WITH_COVERAGE%"=="1" (
  if "%ARTIFACTS_DIR%"=="" (
    set "BACKEND_COVERAGE_PATH=%ROOT_DIR%coverage-backend.json"
  ) else (
    set "BACKEND_COVERAGE_PATH=%ARTIFACTS_DIR%\coverage-backend.json"
  )
)
if "%WITH_COVERAGE%"=="1" (
  if "%ARTIFACTS_DIR%"=="" (
    python -m pytest "%ROOT_DIR%app\backend\tests" -q --cov=app/backend/app --cov-report=term --cov-report=json:"%BACKEND_COVERAGE_PATH%"
  ) else (
    python -m pytest "%ROOT_DIR%app\backend\tests" -q --junitxml "%BACKEND_JUNIT_PATH%" --cov=app/backend/app --cov-report=term --cov-report=json:"%BACKEND_COVERAGE_PATH%"
  )
) else (
  if "%ARTIFACTS_DIR%"=="" (
    python -m pytest "%ROOT_DIR%app\backend\tests" -q
  ) else (
    python -m pytest "%ROOT_DIR%app\backend\tests" -q --junitxml "%BACKEND_JUNIT_PATH%"
  )
)
if errorlevel 1 exit /b %errorlevel%

echo [verify] backend benchmark
python "%ROOT_DIR%scripts\benchmark_backend.py" --payload binary --assert-ms 100
if errorlevel 1 exit /b %errorlevel%

cd /d "%ROOT_DIR%app\frontend"

echo [verify] frontend typecheck
npm.cmd exec tsc -- --noEmit -p .
if errorlevel 1 exit /b %errorlevel%

echo [verify] frontend unit tests
npm.cmd run test:unit
if errorlevel 1 exit /b %errorlevel%

if "%SKIP_BUILD%"=="0" (
  echo [verify] frontend build
  npm.cmd run build
  if errorlevel 1 exit /b %errorlevel%
)

if "%WITH_E2E%"=="1" (
  echo [verify] playwright e2e
  python "%ROOT_DIR%scripts\run_frontend_e2e.py" --skip-build
  if errorlevel 1 exit /b %errorlevel%
)

if "%WITH_LIGHTHOUSE%"=="1" (
  echo [verify] lighthouse ci
  python "%ROOT_DIR%scripts\run_lighthouse_ci.py"
  if errorlevel 1 exit /b %errorlevel%
)

cd /d "%ROOT_DIR%"

if "%SKIP_SMOKE%"=="0" (
  echo [verify] local smoke
  python "%ROOT_DIR%scripts\run_local_smoke.py" --skip-build
  if errorlevel 1 exit /b %errorlevel%
)

if "%WITH_DOCKER%"=="1" (
  echo [verify] docker compose secure flow
  python "%ROOT_DIR%scripts\verify_docker_compose.py"
  if errorlevel 1 exit /b %errorlevel%
)

if "%WITH_DOCKER_PRESERVE%"=="1" (
  echo [verify] docker compose secure flow (preserve)
  python "%ROOT_DIR%scripts\verify_docker_compose.py" --preserve
  if errorlevel 1 exit /b %errorlevel%
)

echo [verify] all checks passed
exit /b 0
