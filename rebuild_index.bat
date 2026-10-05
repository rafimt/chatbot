@echo off
REM Rebuild the search index from the PDFs (only needed for new or different PDFs).
REM CPU: ~30 s per page (hours for all). NVIDIA GPU: see requirements-ocr.txt for the fast option.
setlocal
cd /d "%~dp0"
if not exist ".venv\installed.ok" (
    echo Run start.bat once first, to set up the environment.
    pause
    exit /b 1
)
echo Installing OCR packages...
.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt --quiet || goto :fail

choice /m "Start over (delete the old OCR text)? Choose N to only add new PDFs"
if %errorlevel%==1 del /q "backend\data\pages.jsonl" 2>nul

.venv\Scripts\python.exe backend\ocr.py || goto :fail
.venv\Scripts\python.exe backend\index.py || goto :fail
echo.
echo Done. Restart the app with start.bat.
pause
exit /b 0

:fail
echo [ERROR] Rebuild failed. See the messages above.
pause
exit /b 1
