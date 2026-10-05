@echo off
REM Build dist\Noakhali_QA_RAG_v2.zip to send to someone who already has the PDFs.
REM Includes .env WITH YOUR API KEYS so the app works right away.
REM Excludes: PDFs, .venv, frontend/, caches, logs.
setlocal
cd /d "%~dp0"
set "NAME=Noakhali_QA_RAG_v2"
set "STAGE=dist\%NAME%"
if exist dist rmdir /s /q dist
mkdir "%STAGE%"

robocopy backend "%STAGE%\backend" /e /xd __pycache__ /xf extract_cache.json *.log /njh /njs /nfl /ndl >nul
robocopy web "%STAGE%\web" /e /njh /njs /nfl /ndl >nul
robocopy models "%STAGE%\models" /e /njh /njs /nfl /ndl >nul
for %%f in (questions.json requirements.txt requirements-ocr.txt .env .env.example start.bat rebuild_index.bat README.md HOW_IT_WORKS.md Dockerfile .dockerignore deploy_hf.py) do copy "%%f" "%STAGE%\" >nul
mkdir "%STAGE%\Coastal_Noakhali"
echo Put the 81 plantation journal PDFs in this folder.> "%STAGE%\Coastal_Noakhali\PUT_PDFS_HERE.txt"

powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%\*' -DestinationPath 'dist\%NAME%.zip' -Force"
rmdir /s /q "%STAGE%"
for %%A in (dist\%NAME%.zip) do echo Created dist\%NAME%.zip (%%~zA bytes)
pause
