@echo off
REM =====================================================================
REM  Backend FastAPI - Sistema de Videovigilancia CV
REM  Uso:  doble clic en iniciar_backend.bat
REM =====================================================================
cd /d "%~dp0"

echo.
echo ==========================================
echo   VIGILANCIA CV - Backend (FastAPI)
echo ==========================================
echo.

if not exist ".venv" (
    echo [ERROR] No existe el entorno virtual .venv
    echo Ejecuta primero:  python -m venv .venv
    echo                  .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo Iniciando API en http://127.0.0.1:8000  (documentacion en /docs)
echo.
uvicorn backend.main:app --host 0.0.0.0 --port 8000

pause
