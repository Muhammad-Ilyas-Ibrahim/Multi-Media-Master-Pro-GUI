@echo off
REM ============================================================
REM  Multi-Media-Master-Pro v1.2 - GUI build script
REM  Produces dist\MultiMediaMasterPro\MultiMediaMasterPro.exe
REM ============================================================
setlocal

echo ========================================
echo  Multi-Media-Master-Pro - Build
echo ========================================
echo.

REM --- 1. Python check ---
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    pause
    exit /b 1
)
echo [1/5] Python found:
python --version
echo.

REM --- 2. Dependencies ---
echo [2/5] Installing / checking dependencies...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller!
        pause
        exit /b 1
    )
)
echo.

REM --- 3. Icon ---
echo [3/5] Checking icon.ico...
if not exist "icon.ico" (
    echo WARNING: icon.ico not found - building without a custom icon.
    set "ICON_ARG="
) else (
    echo icon.ico found.
    set "ICON_ARG=--icon=icon.ico"
)
echo.

REM --- 4. ffmpeg ---
echo [4/5] Checking ffmpeg.exe...
if not exist "ffmpeg.exe" (
    echo WARNING: ffmpeg.exe not found next to this script.
    echo          The app will look for ffmpeg on PATH at runtime.
    set "FFMPEG_ARG="
) else (
    echo ffmpeg.exe found - it will be bundled.
    set "FFMPEG_ARG=--add-data ffmpeg.exe;."
)
echo.

REM --- 5. Build ---
echo [5/5] Building executable (this can take a few minutes)...
echo.
python -m PyInstaller ^
    --name=MultiMediaMasterPro ^
    --onedir ^
    --windowed ^
    --noconsole ^
    --clean ^
    --noconfirm ^
    %ICON_ARG% ^
    %FFMPEG_ARG% ^
    --collect-all PyQt5 ^
    --collect-all qtawesome ^
    --hidden-import=PyQt5.QtMultimedia ^
    --hidden-import=PyQt5.QtMultimediaWidgets ^
    main.py

if errorlevel 1 (
    echo.
    echo ERROR: Build failed! See the messages above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build completed successfully!
echo ========================================
echo.
echo  Executable: dist\MultiMediaMasterPro\MultiMediaMasterPro.exe
echo.
echo  If you did NOT bundle ffmpeg.exe, copy it next to the .exe.
echo.
pause
endlocal
