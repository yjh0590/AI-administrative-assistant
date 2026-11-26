@echo off
rem Kaiyon PC photo mode: Windows OCR here, timetable saved to the server (KAIYON_REMOTE in .env).
cd /d "%~dp0"
start "Kaiyon PC" /min .venv\Scripts\python.exe app.py
rem Wait until the server answers (first start can be slow), then open the timetable page.
powershell -NoProfile -Command "for($i=0;$i -lt 120;$i++){try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/ -TimeoutSec 2 | Out-Null; break}catch{Start-Sleep -Milliseconds 500}}"
start "" "http://127.0.0.1:8080/#school"
