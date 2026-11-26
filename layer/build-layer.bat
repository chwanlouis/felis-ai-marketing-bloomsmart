@echo off
setlocal

echo Starting AWS Lambda Layer build process for Linux/AWS Lambda (Python 3.14)...

:: 1. Clean existing layer directory if present
if exist "lambda_layer" (
    echo Cleaning existing lambda_layer directory...
    rmdir /s /q "lambda_layer"
)

:: 2. Create the required Lambda Layer directory structure
echo Creating directory structure: lambda_layer\python
mkdir "lambda_layer\python"

:: 3. Install requirements targeting Linux manylinux for AWS Lambda (Python 3.14)
echo Installing Linux-compatible dependencies from requirements.txt...
pip install -r requirements.txt --target="lambda_layer\python" --platform manylinux_2_17_x86_64 --implementation cp --python-version 3.14 --only-binary=:all: --upgrade

:: 4. Remove old zip if present
if exist "felis-ai-marketing-lambda-layer.zip" (
    del /f /q "felis-ai-marketing-lambda-layer.zip"
)

:: 5. Compress the package into a zip file using Windows built-in PowerShell compression
echo Compressing layer into felis-ai-marketing-lambda-layer.zip...
powershell -Command "Compress-Archive -Path 'lambda_layer\python' -DestinationPath 'felis-ai-marketing-lambda-layer.zip' -Force"

echo Build complete! Linux-compatible layer package ready: %cd%\felis-ai-marketing-lambda-layer.zip
pause