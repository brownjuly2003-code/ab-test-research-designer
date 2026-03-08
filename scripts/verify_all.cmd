@echo off
setlocal

set "SKIP_SMOKE=0"
set "SKIP_BUILD=0"
set "WITH_E2E=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--skip-smoke" set "SKIP_SMOKE=1"
if /I "%~1"=="--skip-build" set "SKIP_BUILD=1"
if /I "%~1"=="--with-e2e" set "WITH_E2E=1"
shift
goto parse_args

:args_done
set "ROOT_DIR=%CD%\"
if not exist "%ROOT_DIR%scripts\generate_frontend_api_types.py" (
  for %%I in ("%~f0") do set "SCRIPT_DIR=%%~dpI"
  for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"
)

echo [verify] generated api contracts
python "%ROOT_DIR%scripts\generate_frontend_api_types.py" --check
if errorlevel 1 exit /b %errorlevel%

echo [verify] generated api docs
python "%ROOT_DIR%scripts\generate_api_docs.py" --check
if errorlevel 1 exit /b %errorlevel%

echo [verify] backend tests
python -m pytest "%ROOT_DIR%app\backend\tests" -q
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
  npm.cmd run test:e2e
  if errorlevel 1 exit /b %errorlevel%
)

cd /d "%ROOT_DIR%"

if "%SKIP_SMOKE%"=="0" (
  echo [verify] local smoke
  python "%ROOT_DIR%scripts\run_local_smoke.py" --skip-build
  if errorlevel 1 exit /b %errorlevel%
)

echo [verify] all checks passed
exit /b 0
