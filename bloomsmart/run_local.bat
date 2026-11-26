@echo off
setlocal

pushd "%~dp0"

if not exist ".env" (
    echo ERROR: .env was not found in %CD%.
    set "EXIT_CODE=1"
    goto :finish
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" set "%%A=%%B"
)

if not defined AWS_REGION set "AWS_REGION=ap-southeast-2"
if not defined DYNAMODB_TABLE_SESSION set "DYNAMODB_TABLE_SESSION=felis_sessions"
if not defined BLOOMSMART_PORT set "BLOOMSMART_PORT=8070"

if exist "..\..\.venv\Scripts\python.exe" (
    set "PYTHON=..\..\.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo Running DynamoDB and S3 connectivity checks...
"%PYTHON%" "..\scripts\test_aws_connections.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto :finish

echo Starting Bloomsmart webapp at http://127.0.0.1:%BLOOMSMART_PORT%
"%PYTHON%" -m uvicorn lambda_function:app --host 127.0.0.1 --port %BLOOMSMART_PORT%
set "EXIT_CODE=%ERRORLEVEL%"

:finish
popd
endlocal & exit /b %EXIT_CODE%
