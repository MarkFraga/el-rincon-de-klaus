@echo off
title El Rincon de Klaus - Setup
color 0A
echo.
echo  ==========================================
echo    EL RINCON DE KLAUS - CONFIGURACION
echo  ==========================================
echo.

echo  Instalando dependencias Python...
pip install -r requirements.txt
echo.

echo  Verificando ffmpeg...
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo  Instalando ffmpeg...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
) else (
    echo  ffmpeg ya esta instalado.
)
echo.

echo  Creando carpeta output...
if not exist output mkdir output

echo.
echo  ==========================================
echo    CONFIGURACION COMPLETA
echo    Ejecuta: python run.py
echo  ==========================================
pause
