#!/bin/bash

# Forex Trading AI System - Environment Setup Script
# This script will set up the complete environment for the Forex Trading AI System

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"  # Change to script directory

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Banner function
print_banner() {
    echo -e "${BLUE}"
    echo "============================================================"
    echo "        Forex Trading AI System - Environment Setup         "
    echo "============================================================"
    echo -e "${NC}"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install system dependencies based on OS
install_system_dependencies() {
    echo -e "${YELLOW}Installing system dependencies...${NC}"
    
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "Detected Linux OS. Installing dependencies..."
        sudo apt update
        sudo apt install -y python3 python3-pip python3-venv nodejs npm docker.io docker-compose curl wget git build-essential
    
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "Detected macOS. Installing dependencies..."
        if ! command_exists brew; then
            echo "Homebrew not found. Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        brew update
        brew install python3 node docker docker-compose wget git
    
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        echo "Detected Windows. Please ensure you have installed:"
        echo "- Python 3.9+"
        echo "- Node.js 18+"
        echo "- Docker Desktop"
        echo "- Git"
        read -p "Press Enter to continue once these are installed..."
    
    else
        echo -e "${RED}Unsupported OS. Please install dependencies manually.${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}System dependencies installed successfully.${NC}"
}

# Function to set up Python virtual environment
setup_python_venv() {
    echo -e "${YELLOW}Setting up Python virtual environment...${NC}"
    
    if [[ -d "venv" ]]; then
        echo "Virtual environment already exists. Activating..."
    else
        echo "Creating new virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate virtual environment based on OS
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi
    
    # Upgrade pip and basic packages
    pip install --upgrade pip setuptools wheel
    
    echo -e "${GREEN}Python virtual environment set up successfully.${NC}"
}

# Function to install TA-Lib
install_talib() {
    echo -e "${YELLOW}Installing TA-Lib...${NC}"
    
    # Execute the dedicated TA-Lib installation script
    if [[ -f "install_talib.sh" ]]; then
        bash ./install_talib.sh
    else
        echo -e "${RED}TA-Lib installation script not found.${NC}"
        exit 1
    fi
}

# Function to install Python dependencies
install_python_dependencies() {
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    
    # Check if requirements.txt exists
    if [[ ! -f "requirements.txt" ]]; then
        echo -e "${RED}requirements.txt not found.${NC}"
        exit 1
    fi
    
    # Install dependencies from requirements.txt
    pip install -r requirements.txt
    
    echo -e "${GREEN}Python dependencies installed successfully.${NC}"
}

# Function to install Node.js dependencies
install_node_dependencies() {
    echo -e "${YELLOW}Installing Node.js dependencies...${NC}"
    
    # Check if package.json exists
    if [[ ! -f "package.json" ]]; then
        echo -e "${RED}package.json not found.${NC}"
        exit 1
    }
    
    # Install Node.js dependencies
    npm install
    
    echo -e "${GREEN}Node.js dependencies installed successfully.${NC}"
}

# Function to configure environment variables
configure_environment() {
    echo -e "${YELLOW}Configuring environment variables...${NC}"
    
    # Check if .env.example exists
    if [[ ! -f ".env.example" ]]; then
        echo -e "${RED}.env.example not found.${NC}"
        exit 1
    }
    
    # Create .env file if it doesn't exist
    if [[ ! -f ".env" ]]; then
        cp .env.example .env
        echo -e "${GREEN}.env file created from .env.example${NC}"
        echo -e "${YELLOW}Please edit the .env file with your API keys and configuration settings.${NC}"
        sleep 2
        
        # Open .env file for editing
        if command_exists nano; then
            nano .env
        elif command_exists vim; then
            vim .env
        elif command_exists code; then
            code .env
        else
            echo -e "${YELLOW}Please open and edit the .env file manually.${NC}"
        fi
    else
        echo ".env file already exists."
    fi
    
    echo -e "${GREEN}Environment configuration completed.${NC}"
}

# Function to initialize databases
initialize_databases() {
    echo -e "${YELLOW}Initializing databases...${NC}"
    
    # Start database containers with Docker Compose
    if command_exists docker-compose; then
        docker-compose up -d postgres mongodb redis
        
        # Wait for databases to be ready
        echo "Waiting for databases to be ready..."
        sleep 10
        
        # Initialize database schemas
        if [[ -f "src/tools/db_init.py" ]]; then
            python -m src.tools.db_init
        else
            echo -e "${YELLOW}Database initialization script not found. Skipping...${NC}"
        fi
        
        echo -e "${GREEN}Databases initialized successfully.${NC}"
    else
        echo -e "${RED}Docker Compose not found. Please install Docker and Docker Compose.${NC}"
        exit 1
    fi
}

# Function to start the system
start_system() {
    echo -e "${YELLOW}Starting the Forex Trading AI System...${NC}"
    
    if command_exists docker-compose; then
        # Ensure all containers are down first
        docker-compose down
        
        # Start all services
        docker-compose up -d
        
        echo -e "${GREEN}System started successfully.${NC}"
        echo -e "${BLUE}Access the dashboard at:${NC}"
        echo -e "  - FastAPI: http://localhost:8000/"
        echo -e "  - Flask: http://localhost:5000/"
        
        # Start the agent swarm in paper trading mode
        echo -e "${YELLOW}Starting AI trading agents in paper trading mode...${NC}"
        if [[ -f "src/cli/agent_launcher.py" ]]; then
            python -m src.cli.agent_launcher --mode paper --pairs EURUSD,GBPUSD,USDJPY --count 5
            
            echo -e "${GREEN}AI trading agents started successfully.${NC}"
        else
            echo -e "${YELLOW}Agent launcher script not found. Skipping...${NC}"
        fi
    else
        echo -e "${RED}Docker Compose not found. Please install Docker and Docker Compose.${NC}"
        exit 1
    fi
}

# Function to display system status
check_system_status() {
    echo -e "${YELLOW}Checking system status...${NC}"
    
    if command_exists docker-compose; then
        # Check container status
        docker-compose ps
        
        # Check API health
        if command_exists curl; then
            echo -e "${YELLOW}Checking API health...${NC}"
            curl -s http://localhost:8000/health || echo -e "${RED}API is not responding.${NC}"
        fi
    else
        echo -e "${RED}Docker Compose not found. Cannot check system status.${NC}"
    fi
}

# Main execution
print_banner

# Execute setup steps
install_system_dependencies
setup_python_venv
install_talib
install_python_dependencies
install_node_dependencies
configure_environment
initialize_databases
start_system
check_system_status

echo -e "${GREEN}"
echo "============================================================"
echo "       Forex Trading AI System setup completed!             "
echo "============================================================"
echo -e "${NC}"
echo "If you encounter any issues, please check the logs directory or run:"
echo "  docker-compose logs -f"
echo ""
echo "To stop the system:"
echo "  ./src/cli/safe_shutdown.py   # Graceful shutdown"
echo "  or"
echo "  docker-compose down          # Quick shutdown"
echo ""
echo "Happy trading!" 