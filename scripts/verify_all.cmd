@echo off
setlocal

set "SKIP_SMOKE=0"
set "SKIP_BUILD=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--skip-smoke" set "SKIP_SMOKE=1"
if /I "%~1"=="--skip-build" set "SKIP_BUILD=1"
shift
goto parse_args

:args_done
cd /d "%~dp0\.."

echo [verify] generated api contracts
python scripts\generate_frontend_api_types.py --check
if errorlevel 1 exit /b %errorlevel%

echo [verify] backend tests
python -m pytest app/backend/tests -q
if errorlevel 1 exit /b %errorlevel%

cd /d app\frontend

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

cd /d "..\.."

if "%SKIP_SMOKE%"=="0" (
  echo [verify] local smoke
  python scripts\run_local_smoke.py --skip-build
  if errorlevel 1 exit /b %errorlevel%
)

echo [verify] all checks passed
exit /b 0
