@echo off
REM =====================================================================
REM  Respaldo completo de la base de datos vigilancia_cv
REM  Uso:  doble clic en  respaldo.bat  (o programalo en el Planificador)
REM
REM  Un solo dump incluye datos, fotos de registro y snapshots, porque
REM  todo vive en MySQL como LONGBLOB.
REM =====================================================================
cd /d "%~dp0"

set MYSQL_BIN=C:\wamp64\bin\mysql\mysql8.4.7\bin\mysqldump.exe

if not exist "backups" mkdir backups

set ARCHIVO=backups\vigilancia_%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%.sql

echo Respaldando en %ARCHIVO% ...
"%MYSQL_BIN%" -u vigilancia -pvigilancia123 --single-transaction --routines ^
    --triggers --max_allowed_packet=64M --default-character-set=utf8mb4 ^
    vigilancia_cv > "%ARCHIVO%"

if exist "%ARCHIVO%" (
    echo.
    echo OK - Respaldo creado: %ARCHIVO%
) else (
    echo ERROR - No se pudo crear el respaldo.
)
pause
