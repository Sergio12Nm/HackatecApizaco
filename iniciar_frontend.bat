@echo off
REM =====================================================================
REM  Frontend Streamlit - Sistema de Videovigilancia CV
REM  Uso:  doble clic en iniciar_frontend.bat
REM =====================================================================
cd /d "%~dp0"

echo.
echo ==========================================
echo   VIGILANCIA CV - Interfaz (Streamlit)
echo ==========================================
echo.

if not exist ".venv" (
    echo [ERROR] No existe el entorno virtual .venv
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo Interfaz en http://localhost:8501
echo.
streamlit run frontend\app.py --server.address 0.0.0.0 --server.port 8501

pause
