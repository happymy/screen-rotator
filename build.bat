@echo off
chcp 65001 >nul
echo ========================================
echo   Screen Rotator Build Script
echo ========================================
echo.

REM Create/activate virtual environment
if not exist venv_pack (
    echo Creating virtual environment...
    python -m venv venv_pack
)
call venv_pack\Scripts\activate

REM Install dependencies
echo Installing dependencies...
pip install --upgrade rotate-screen customtkinter pyinstaller
if %errorlevel% neq 0 (
    echo Dependency installation failed. Check network.
    pause
    exit /b 1
)

REM Clean old builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build EXE
echo Building EXE...
pyinstaller --onefile --windowed --name "ScreenRotator" ^
    --uac-admin ^
    --collect-data customtkinter ^
    --exclude-module matplotlib ^
    --exclude-module PIL ^
    --exclude-module tkinter.test ^
    --clean ^
    screen_rotator.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   Build Successful!
    echo   Output: dist\ScreenRotator.exe
    echo ========================================
) else (
    echo.
    echo Build Failed. Check error messages.
)

pause