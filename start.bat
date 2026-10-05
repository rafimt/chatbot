@echo off
setlocal
title Noakhali Plantation Q^&A
cd /d "%~dp0"
set "VENV_PY=%CD%\.venv\Scripts\python.exe"

REM ---------------------------------------------------------------
REM  Already running? Just open the browser.
REM ---------------------------------------------------------------
netstat -ano | findstr ":8000 " | findstr LISTENING >nul
if %errorlevel%==0 (
    echo The app is already running. Opening the browser...
    start "" http://localhost:8000
    exit /b 0
)

REM ---------------------------------------------------------------
REM  First run: set up Python environment automatically
REM ---------------------------------------------------------------
REM installed.ok holds a copy of requirements.txt: if the requirements changed, install again
if exist ".venv\installed.ok" (
    fc /b requirements.txt ".venv\installed.ok" >nul 2>&1 && goto :env
    if exist "%VENV_PY%" (
        echo Requirements changed, updating packages...
        "%VENV_PY%" -m pip install -r requirements.txt --quiet || goto :setup_failed
        copy /y requirements.txt ".venv\installed.ok" >nul
        goto :env
    )
)

echo.
echo === First run: setting up (this happens only once, 3-10 minutes) ===
call :find_python
if not defined PY (
    echo Python 3.10+ was not found. Installing Python 3.11 with winget...
    winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
    set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)
%PY% -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Could not install Python automatically.
    echo Please install Python 3.11 from https://www.python.org/downloads/
    echo ^(tick "Add Python to PATH"^), then run start.bat again.
    pause
    exit /b 1
)
echo Using Python: %PY%

if not exist "%VENV_PY%" (
    echo Creating virtual environment...
    %PY% -m venv .venv || goto :setup_failed
)
echo Installing packages...
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install -r requirements.txt --quiet || goto :setup_failed
copy /y requirements.txt ".venv\installed.ok" >nul
echo Setup complete.

REM ---------------------------------------------------------------
REM  API keys
REM ---------------------------------------------------------------
:env
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo === Add your API keys ===
    echo Notepad will open. Paste your Groq and OpenRouter keys, save, and close Notepad.
    start /wait notepad ".env"
)
findstr /r "^GROQ_API_KEY=. ^LLM_API_KEY=." ".env" >nul
if errorlevel 1 (
    echo [WARNING] No API key found in .env. The chatbot cannot answer until you add one.
)

REM ---------------------------------------------------------------
REM  Check PDFs (warning only) and start
REM ---------------------------------------------------------------
echo.
"%VENV_PY%" backend\check_pdfs.py
echo.
echo Starting the app at http://localhost:8000  (close this window to stop it)
start "" cmd /c "timeout /t 8 /nobreak >nul & start http://localhost:8000"
"%VENV_PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
exit /b 0

REM ---------------------------------------------------------------
:find_python
REM Prefer the Python launcher, then python on PATH (skip the Microsoft Store stub)
set "PY="
py -3.11 -c "import sys" >nul 2>&1 && (set "PY=py -3.11" & exit /b 0)
py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1 && (set "PY=py -3" & exit /b 0)
python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1 && (set "PY=python" & exit /b 0)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
exit /b 0

:setup_failed
echo.
echo [ERROR] Setup failed. Check your internet connection and run start.bat again.
echo If it keeps failing, delete the .venv folder and try once more.
pause
exit /b 1
