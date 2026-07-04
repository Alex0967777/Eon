@echo off
setlocal EnableExtensions

set "EON_REPO=E:\Eon\GitRepo\Eon"
set "SCRIPT=%~dp0Apply-EonMemory.ps1"

if not exist "%SCRIPT%" set "SCRIPT=%EON_REPO%\Apply-EonMemory.ps1"

if not exist "%SCRIPT%" (
    echo Apply-EonMemory.ps1 was not found.
    echo Expected next to this BAT or in %EON_REPO%
    pause
    exit /b 2
)

where pwsh.exe >nul 2>nul
if %errorlevel%==0 (
    set "POWERSHELL_EXE=pwsh.exe"
) else (
    set "POWERSHELL_EXE=powershell.exe"
)

"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -RepositoryRoot "%EON_REPO%"
set "RESULT=%errorlevel%"

echo.
if not "%RESULT%"=="0" (
    echo Apply-EonMemory failed. The patch remains in Downloads.
) else (
    echo Done.
)
pause
exit /b %RESULT%
