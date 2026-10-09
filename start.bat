@echo off
REM Complete startup script for Windows

echo =========================================
echo StockItUp - Comprehensive Startup Script
echo =========================================
echo.

REM Check Docker
echo Step 1: Checking Docker...
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running! Please start Docker Desktop.
    pause
    exit /b 1
)
echo [OK] Docker is running
echo.

REM Check .env file
echo Step 2: Checking .env file...
if not exist .env (
    echo [ERROR] .env file not found!
    echo Creating from .env.example...
    copy .env.example .env
    echo [WARNING] Please edit .env with your API keys!
    pause
    exit /b 1
)
echo [OK] .env file exists
echo.

REM Stop existing containers
echo Step 3: Stopping existing containers...
docker-compose down
echo [OK] Cleanup complete
echo.

REM Build images
echo Step 4: Building Docker images...
echo This may take 2-5 minutes on first run...
docker-compose build --no-cache
if errorlevel 1 (
    echo [ERROR] Build failed!
    pause
    exit /b 1
)
echo [OK] Build successful
echo.

REM Start services
echo Step 5: Starting all services...
docker-compose up -d

REM Wait for services
echo.
echo Waiting for services to be ready...
timeout /t 10 /nobreak >nul

echo.
echo =========================================
echo [SUCCESS] StockItUp is starting!
echo =========================================
echo.
echo Services:
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:8000
echo   Mock API: http://localhost:8001
echo.
echo To view logs: docker-compose logs -f
echo To stop:      docker-compose down
echo.

REM Show status
echo Container Status:
docker-compose ps
echo.

echo ================================
echo [SUCCESS] Startup Complete!
echo ================================
echo.
echo Open http://localhost:3000 to use StockItUp
echo.
pause
