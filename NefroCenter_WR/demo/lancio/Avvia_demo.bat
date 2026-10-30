@echo off
rem Avvia la demo di NefroCenter WR (solo dati fittizi) su questo computer e apre il browser.
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 avvia_demo.py %*
) else (
  python avvia_demo.py %*
)
if errorlevel 1 (
  echo.
  echo La demo non e' partita. Serve Python 3: https://www.python.org/downloads/ (spuntare "Add python.exe to PATH").
  pause
)
endlocal
