<#
.SYNOPSIS
    Instala PyPrinting 3.0 / PySpectrum 3.0 en un entorno virtual de Python 3.11 y verifica el resultado.

.DESCRIPTION
    No toca ningun instrumento: no abre la placa NI, no conecta la platina ni la camara. Solo:
      1. busca Python 3.11 de 64 bits (obligatorio en el banco: pylablib 1.4.3 trae la extension de la
         camara Andor solo para 3.11);
      2. crea el entorno virtual (.venv en la raiz del repositorio, salvo -VenvDir);
      3. instala requirements.txt y despues pylablib 1.4.3 con --no-deps (sus dependencias pyft232 y PyQt5
         rompen la instalacion; ver requirements.txt);
      4. quita pyft232 y PyQt5 si quedaron de una instalacion anterior;
      5. verifica que cada modulo se importe, incluida la camara por pylablib;
      6. revisa los requisitos del sistema (driver NI-DAQmx, DLL GCS2 de PI, Andor Solis, SPECTROG.INI,
         EDSDK) sin abrir ningun dispositivo, y avisa lo que falta;
      7. guarda un informe con las versiones en logs\instalacion_<fecha>.log (sirve para BANCO-23).

    Se puede correr de nuevo sobre un entorno existente: actualiza lo que falte.

.PARAMETER Python
    Ruta a un python.exe 3.11. Si se omite, se busca con el lanzador "py -3.11".

.PARAMETER VenvDir
    Carpeta del entorno virtual. Por defecto, .venv en la raiz del repositorio.

.PARAMETER Opcional
    Instala tambien requirements-opcional.txt (picasso).

.PARAMETER AccesoDirecto
    Crea en el Escritorio un acceso directo "PyPrinting 3.0" a iniciar_pyprinting.bat.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\install\instalar.ps1 -AccesoDirecto
#>
[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$VenvDir = "",
    [switch]$Opcional,
    [switch]$AccesoDirecto
)

# "Continue": en PowerShell 5.1, con "Stop" cualquier linea de stderr de un programa externo (pip, python)
# aborta el script. Cada paso revisa $LASTEXITCODE.
$ErrorActionPreference = "Continue"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $VenvDir) { $VenvDir = Join-Path $RepoRoot ".venv" }
$PylablibVersion = "1.4.3"
$Problemas = New-Object System.Collections.Generic.List[string]
$Avisos = New-Object System.Collections.Generic.List[string]
$Informe = New-Object System.Collections.Generic.List[string]

function Paso([string]$texto) { Write-Host ""; Write-Host "== $texto" -ForegroundColor Cyan }
function Bien([string]$texto) { Write-Host "   OK    $texto" -ForegroundColor Green; $Informe.Add("OK     $texto") }
function Aviso([string]$texto) { Write-Host "   AVISO $texto" -ForegroundColor Yellow; $Avisos.Add($texto); $Informe.Add("AVISO  $texto") }
function Falla([string]$texto) { Write-Host "   FALLA $texto" -ForegroundColor Red; $Problemas.Add($texto); $Informe.Add("FALLA  $texto") }

function Invocar([string]$exe, [string[]]$argumentos, [string]$que) {
    & $exe @argumentos
    if ($LASTEXITCODE -ne 0) { throw "$que termino con codigo $LASTEXITCODE" }
}

# Devuelve "3.11|64" para el interprete dado, o $null si no corre.
function VersionDe([string]$exe) {
    try {
        $salida = & $exe -c "import sys, struct; print('%d.%d|%d' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P') * 8))" 2>$null
        if ($LASTEXITCODE -eq 0) { return ($salida | Select-Object -Last 1).Trim() }
    } catch { }
    return $null
}

Write-Host "Instalador de PyPrinting 3.0 / PySpectrum 3.0" -ForegroundColor Cyan
Write-Host "Repositorio: $RepoRoot"
Write-Host "Entorno:     $VenvDir"

# -- 1. Python 3.11 de 64 bits ------------------------------------------------
Paso "1. Python 3.11 de 64 bits"
if (-not $Python) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $ruta = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ruta) { $Python = ($ruta | Select-Object -Last 1).Trim() }
        } catch { }
    }
}
if (-not $Python) {
    Write-Host "No se encontro Python 3.11. Instalarlo desde python.org (Windows installer 64-bit, 3.11.x)," -ForegroundColor Red
    Write-Host "con el lanzador 'py', o pasar la ruta con -Python C:\ruta\python.exe" -ForegroundColor Red
    exit 1
}
$ver = VersionDe $Python
if ($ver -ne "3.11|64") {
    Write-Host "El interprete $Python es '$ver'; hace falta 3.11 de 64 bits (pylablib 1.4.3 + camara Andor)." -ForegroundColor Red
    exit 1
}
Bien "Python 3.11 64 bits: $Python"

# -- 2. Entorno virtual ------------------------------------------------------
Paso "2. Entorno virtual"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (Test-Path $VenvPython) {
    $verVenv = VersionDe $VenvPython
    if ($verVenv -ne "3.11|64") {
        Write-Host "Ya existe un entorno en $VenvDir con Python '$verVenv'." -ForegroundColor Red
        Write-Host "No se borra solo: renombrarlo o borrarlo a mano, o elegir otra carpeta con -VenvDir." -ForegroundColor Red
        exit 1
    }
    Bien "se reutiliza el entorno existente"
} else {
    Invocar $Python @("-m", "venv", $VenvDir) "La creacion del entorno"
    Bien "entorno creado"
}

# -- 3. Dependencias ---------------------------------------------------------
Paso "3. Dependencias"
Invocar $VenvPython @("-m", "pip", "install", "--upgrade", "pip") "La actualizacion de pip"
Invocar $VenvPython @("-m", "pip", "install", "-r", (Join-Path $RepoRoot "requirements.txt")) "pip install -r requirements.txt"
Invocar $VenvPython @("-m", "pip", "install", "--no-deps", "pylablib==$PylablibVersion") "pip install pylablib"
if ($Opcional) {
    # Junto con requirements.txt, para que pip respete la serie de PyQt6 fijada ahi.
    Invocar $VenvPython @("-m", "pip", "install", "-r", (Join-Path $RepoRoot "requirements.txt"), "-r", (Join-Path $RepoRoot "requirements-opcional.txt")) "pip install -r requirements-opcional.txt"
}
Bien "dependencias instaladas"

# -- 4. Paquetes que no deben estar ------------------------------------------
Paso "4. Paquetes que rompen el entorno (pyft232, PyQt5)"
foreach ($pkg in @("pyft232", "PyQt5", "PyQt5-sip", "PyQt5-Qt5")) {
    & $VenvPython -m pip show $pkg *> $null
    if ($LASTEXITCODE -eq 0) {
        Invocar $VenvPython @("-m", "pip", "uninstall", "-y", $pkg) "pip uninstall $pkg"
        Bien "se quito $pkg"
    }
}
Bien "sin pyft232 ni PyQt5"

# -- 5. Importaciones --------------------------------------------------------
Paso "5. Importaciones (sin abrir ningun dispositivo)"
$modulos = [ordered]@{
    "PyQt6"                      = "from PyQt6 import QtCore, QtWidgets"
    # Como en la aplicacion: WebEngine se importa con la QApplication ya creada (wiki con MathJax).
    "PyQt6-WebEngine (wiki)"     = "import os, sys; os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen'); from PyQt6 import QtWidgets; a = QtWidgets.QApplication(sys.argv); from PyQt6.QtWebEngineWidgets import QWebEngineView"
    "pyqtgraph"                  = "import pyqtgraph"
    "numpy / scipy / pandas"     = "import numpy, scipy, pandas"
    "numba"                      = "import numba"
    "h5py"                       = "import h5py"
    "OpenCV / scikit-image"      = "import cv2, skimage"
    "trackpy"                    = "import trackpy"
    "sif_parser"                 = "import sif_parser"
    "nidaqmx"                    = "import nidaqmx"
    "pipython"                   = "import pipython"
    "camara Andor por pylablib"  = "from pylablib.devices.Andor import AndorSDK2Camera"
}
foreach ($nombre in $modulos.Keys) {
    & $VenvPython -c $modulos[$nombre] *> $null
    if ($LASTEXITCODE -eq 0) { Bien $nombre } else { Falla "no se importa: $nombre ($($modulos[$nombre]))" }
}
& $VenvPython -c "import picasso.localize" *> $null
if ($LASTEXITCODE -eq 0) { Bien "picasso (opcional)" } else { $Informe.Add("--     picasso (opcional) no instalado") }

# -- 6. Requisitos del sistema -----------------------------------------------
Paso "6. Requisitos del sistema (solo se leen; ningun dispositivo se abre)"
$niVer = & $VenvPython -c "import nidaqmx.system as s; print(s.System.local().driver_version)" 2>$null
if ($LASTEXITCODE -eq 0 -and $niVer) { Bien "driver NI-DAQmx: $($niVer | Select-Object -Last 1)" }
else { Aviso "no se pudo leer el driver NI-DAQmx: instalar NI-DAQmx (sin el, solo funciona el modo seguro)" }

$piDll = & $VenvPython -c "from pipython import GCSDevice; d = GCSDevice(); print(d.dllver)" 2>$null
if ($LASTEXITCODE -eq 0) { Bien "DLL GCS2 de PI cargada: $(($piDll | Select-Object -Last 1) -replace '\s+', ' ')" }
else { Aviso "no se cargo la DLL GCS2 de PI (PI_GCS2_DLL_x64.dll): instalar el software de PI (PIMikroMove / GCS2)" }

$solis = "C:\Program Files\Andor SOLIS"
if (Test-Path (Join-Path $solis "atmcd64d_legacy.dll")) { Bien "DLL de la camara: $solis\atmcd64d_legacy.dll (la que usa pylablib, igual que el legado)" }
elseif (Test-Path (Join-Path $solis "atmcd64d.dll")) { Bien "DLL de la camara: $solis\atmcd64d.dll" }
else { Aviso "no esta Andor Solis en ${solis}: pylablib no encuentra la DLL de la camara (o definir PYSPECTRUM_ANDOR_DLL_DIR)" }
if (Test-Path (Join-Path $solis "SPECTROG.INI")) { Bien "SPECTROG.INI del Shamrock" }
else { Aviso "falta $solis\SPECTROG.INI: el Shamrock arranca sin su archivo de configuracion" }

$shamrock = Join-Path $RepoRoot "pyspectrum\drivers\libs\Windows\64"
foreach ($dll in @("ShamrockCIF.dll", "atshamrock.dll")) {
    if (Test-Path (Join-Path $shamrock $dll)) { Bien "Shamrock: $dll" } else { Falla "falta $shamrock\$dll" }
}
$edsdk = Join-Path $RepoRoot "ESDK_CANON\EDSDK_v13.20.21_Windows\EDSDK_64\Dll\EDSDK.dll"
if (Test-Path $edsdk) { Bien "EDSDK de Canon" } else { Aviso "falta EDSDK.dll de Canon: la Suite de Camara no ve la camara reflex" }

if ($env:PYSPECTRUM_ANDOR_BACKEND) { Aviso "PYSPECTRUM_ANDOR_BACKEND='$($env:PYSPECTRUM_ANDOR_BACKEND)': en el banco no debe estar definida (BANCO-23)" }
if ($env:PYPRINTING_SAFE -eq "1") { Aviso "PYPRINTING_SAFE=1 en este usuario: los programas arrancan en modo seguro (simulado)" }

# -- 7. Acceso directo -------------------------------------------------------
$bat = Join-Path $RepoRoot "iniciar_pyprinting.bat"
if ($AccesoDirecto) {
    Paso "7. Acceso directo en el Escritorio"
    $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "PyPrinting 3.0.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath = $bat
    $sc.WorkingDirectory = $RepoRoot
    $sc.Save()
    Bien "acceso directo: $lnk"
}

# -- Informe -----------------------------------------------------------------
$logDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$logFile = Join-Path $logDir ("instalacion_{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmm"))
$commit = ""
try { $commit = (& git -C $RepoRoot rev-parse --short HEAD 2>$null) } catch { }
$freeze = & $VenvPython -m pip freeze 2>$null
$cabecera = @(
    "Instalacion de PyPrinting 3.0 / PySpectrum 3.0",
    "Fecha:   $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    "Equipo:  $env:COMPUTERNAME",
    "Commit:  $commit",
    "Python:  $Python",
    "Entorno: $VenvDir",
    ""
)
($cabecera + $Informe + @("", "pip freeze:") + $freeze) | Out-File -FilePath $logFile -Encoding utf8

Write-Host ""
if ($Problemas.Count -gt 0) {
    Write-Host "La instalacion termino con $($Problemas.Count) falla(s). Ver $logFile" -ForegroundColor Red
    exit 2
}
if ($Avisos.Count -gt 0) {
    Write-Host "Instalado, con $($Avisos.Count) aviso(s) sobre el sistema. Informe: $logFile" -ForegroundColor Yellow
} else {
    Write-Host "Instalado y verificado. Informe: $logFile" -ForegroundColor Green
}
Write-Host "Para iniciar: $bat  (o .venv\Scripts\python main.py)"
exit 0
