#!/bin/bash
# Complete startup script with error handling

echo "========================================="
echo "StockItUp - Comprehensive Startup Script"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Check Docker
echo "Step 1: Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found! Please install Docker Desktop.${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker is not running! Please start Docker Desktop.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker is running${NC}"
echo ""

# Step 2: Check .env file
echo "Step 2: Checking .env file..."
if [ ! -f .env ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo "Creating from .env.example..."
    cp .env.example .env
    echo -e "${YELLOW}⚠️  Please edit .env with your API keys!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ .env file exists${NC}"
echo ""

# Step 3: Stop existing containers
echo "Step 3: Stopping existing containers..."
docker-compose down 2>/dev/null
echo -e "${GREEN}✅ Cleanup complete${NC}"
echo ""

# Step 4: Build images
echo "Step 4: Building Docker images..."
echo "This may take 2-5 minutes on first run..."
docker-compose build --no-cache
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Build failed!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Build successful${NC}"
echo ""

# Step 5: Start services
echo "Step 5: Starting all services..."
docker-compose up -d

# Wait for services
echo ""
echo "Waiting for services to be ready..."
sleep 5

# Check if containers are running
RUNNING=$(docker-compose ps | grep "Up" | wc -l)
if [ $RUNNING -lt 5 ]; then
    echo -e "${YELLOW}⚠️  Some services may not be ready yet${NC}"
    echo "Checking logs for errors..."
    docker-compose logs backend | tail -20
fi

echo ""
echo "========================================="
echo -e "${GREEN}✅ StockItUp is starting!${NC}"
echo "========================================="
echo ""
echo "Services:"
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8000"
echo "  Mock API: http://localhost:8001"
echo ""
echo "To view logs: docker-compose logs -f"
echo "To stop:      docker-compose down"
echo ""
echo "Waiting 10 seconds for full startup..."
sleep 10

# Show status
echo ""
echo "Container Status:"
docker-compose ps
echo ""

# Test backend
echo "Testing backend health..."
if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend is responding${NC}"
else
    echo -e "${YELLOW}⚠️  Backend may still be starting...${NC}"
    echo "Check logs with: docker-compose logs backend"
fi

echo ""
echo "================================"
echo -e "${GREEN}🚀 Startup Complete!${NC}"
echo "================================"
echo ""
echo "Open http://localhost:3000 to use StockItUp"
echo ""
