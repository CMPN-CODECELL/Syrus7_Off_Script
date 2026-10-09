#!/bin/bash
# StockItUp Pre-Launch Health Check
# Run this before docker-compose to catch issues early

echo "🔍 StockItUp Pre-Launch Health Check"
echo "===================================="
echo ""

ERRORS=0

# Check 1: Required files exist
echo "✓ Checking required files..."
FILES=(
    "docker-compose.yml"
    ".env.example"
    "backend/main.py"
    "backend/requirements.txt"
    "backend/Dockerfile"
    "frontend/package.json"
    "frontend/Dockerfile"
    "frontend/src/app/page.tsx"
    "mock-api/main.py"
    "db/migrations/001_init.sql"
)

for file in "${FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ Missing: $file"
        ERRORS=$((ERRORS + 1))
    fi
done

# Check 2: .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found. Copy .env.example to .env and add your API key"
    ERRORS=$((ERRORS + 1))
else
    echo "✓ .env file exists"

    # Check if API key is set
    if grep -q "ANTHROPIC_API_KEY=your_" .env; then
        echo "⚠️  Warning: ANTHROPIC_API_KEY not configured in .env"
        ERRORS=$((ERRORS + 1))
    else
        echo "✓ API key appears to be set"
    fi
fi

# Check 3: Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop"
    ERRORS=$((ERRORS + 1))
else
    echo "✓ Docker is running"
fi

# Check 4: Required directories exist
echo ""
echo "✓ Checking directory structure..."
DIRS=(
    "backend/agent"
    "backend/services"
    "backend/routers"
    "frontend/src/app"
    "frontend/src/components"
    "frontend/src/lib"
    "frontend/public"
)

for dir in "${DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        echo "❌ Missing directory: $dir"
        mkdir -p "$dir"
        echo "   Created: $dir"
    fi
done

echo ""
echo "===================================="
if [ $ERRORS -eq 0 ]; then
    echo "✅ All checks passed! Ready to launch."
    echo ""
    echo "Run: docker-compose up --build"
else
    echo "❌ Found $ERRORS issue(s). Please fix them before launching."
fi
echo "===================================="
