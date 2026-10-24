@echo off
rem Starts the stepgen app from this folder (no installer needed).
cd /d "%~dp0"
py -3 -c "import PySide6, librosa, mutagen, sounddevice, onnxruntime" 2>nul || py -3 -m pip install -r requirements.txt -r requirements-app.txt
start "" pyw -3 stepgen_app.py %*
