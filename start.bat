@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
    echo Docker was not found. Please install and start Docker Desktop first.
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Created .env from .env.example.
    echo Please configure LLM_API_KEY in .env, then run start.bat again.
    pause
    exit /b 1
)

docker compose up -d --build
if errorlevel 1 (
    echo Failed to start DataPilot. Run docker compose logs for details.
    pause
    exit /b 1
)

docker compose ps
start "" "http://localhost:8080"
echo DataPilot is starting at http://localhost:8080
pause
