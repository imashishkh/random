#!/bin/bash
# Security Module Installation Script

# Colors for better visual feedback
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Forex Trading Security Module Installer${NC}"
echo "This script will install the necessary dependencies for the security module."
echo

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}Node.js is not installed. Please install Node.js first.${NC}"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2)
echo -e "${GREEN}Node.js version ${NODE_VERSION} detected.${NC}"

# Create directory structure if it doesn't exist
mkdir -p src/security/js 2>/dev/null
echo "Directory structure verified."

# Check if package.json exists in the root directory
if [ ! -f "package.json" ]; then
    echo -e "${YELLOW}No package.json found. Creating one...${NC}"
    # Determine project name from directory name
    PROJECT_NAME=$(basename "$(pwd)")
    npm init -y
    echo "Basic package.json created."
fi

echo -e "${YELLOW}Installing required dependencies...${NC}"

# Install dependencies
npm install --save keytar@7.9.0
npm install --save-dev electron-rebuild@3.2.9

# Check if installation was successful
if [ $? -ne 0 ]; then
    echo -e "${RED}Error installing dependencies. See above for details.${NC}"
    echo -e "${YELLOW}Note: keytar requires node-gyp and build tools for native compilation.${NC}"
    echo "You may need to install additional system dependencies:"
    echo "  - On Ubuntu/Debian: sudo apt-get install libsecret-1-dev"
    echo "  - On RedHat/CentOS: sudo yum install libsecret-devel"
    echo "  - On macOS: xcode-select --install"
    echo "  - On Windows: npm install --global --production windows-build-tools"
    exit 1
fi

echo -e "${GREEN}Dependencies installed successfully.${NC}"

# Check for core files
SECURITY_FILES=("errorHandler.js" "secretManager.js" "secureStorage.js" "wizardCompletion.js" "index.js")
MISSING_FILES=false

echo "Checking for required module files:"
for file in "${SECURITY_FILES[@]}"; do
    if [ ! -f "src/security/js/$file" ]; then
        echo -e "${YELLOW}⚠ Missing file: src/security/js/$file${NC}"
        MISSING_FILES=true
    else
        echo -e "${GREEN}✓ Found: src/security/js/$file${NC}"
    fi
done

if [ "$MISSING_FILES" = true ]; then
    echo -e "${YELLOW}Some required files are missing. Please ensure all security module files are in place.${NC}"
else
    echo -e "${GREEN}All required files are present.${NC}"
fi

# Rebuild native modules for Electron (if applicable)
if [ -f "package.json" ] && grep -q "electron" "package.json"; then
    echo -e "${YELLOW}Electron detected. Rebuilding native modules...${NC}"
    npx electron-rebuild
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error rebuilding native modules for Electron.${NC}"
        exit 1
    fi
    echo -e "${GREEN}Native modules rebuilt for Electron.${NC}"
fi

echo -e "${GREEN}Security module installation completed successfully!${NC}"
echo
echo "To get started, import the security components in your application:"
echo -e "${YELLOW}const { SecretManager, SecureStorage, handleError } = require('./src/security/js');${NC}"
echo
echo "See src/security/README.md and src/security/js/examples.js for usage examples." 