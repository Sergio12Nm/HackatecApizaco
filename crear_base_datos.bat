@echo off
REM =====================================================================
REM  Instala la base de datos MySQL (vigilancia_cv) en WampServer
REM  Uso:  doble clic en  crear_base_datos.bat  (ejecuta como ROOT)
REM =====================================================================
cd /d "%~dp0"

set MYSQL_BIN=C:\wamp64\bin\mysql\mysql8.4.7\bin\mysql.exe

if not exist "%MYSQL_BIN%" (
    echo [AVISO] No se encontro "%MYSQL_BIN%".
    echo Busca tu cliente mysql.exe dentro de C:\wamp64\bin\mysql\ y ajustalo aqui.
    pause
    exit /b 1
)

echo Aplicando sql\schema.sql ...
echo (Si MySQL pide clave, es la de ROOT de WampServer)
echo.
"%MYSQL_BIN%" -u root --default-character-set=utf8mb4 -e "source %CD%\sql\schema.sql"

echo.
echo Listo. Base de datos 'vigilancia_cv' creada con el usuario 'vigilancia'.
pause
