#!/bin/bash

# Function to detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

# Install TA-Lib based on OS
install_talib() {
    OS=$(detect_os)
    echo "Detected OS: $OS"
    
    case $OS in
        linux)
            echo "Installing TA-Lib on Linux..."
            sudo apt-get update
            sudo apt-get install -y build-essential wget
            
            # Download and install TA-Lib
            wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
            tar -xzf ta-lib-0.4.0-src.tar.gz
            cd ta-lib/
            ./configure --prefix=/usr
            make
            sudo make install
            cd ..
            rm -rf ta-lib ta-lib-0.4.0-src.tar.gz
            
            # Install Python wrapper
            pip install ta-lib
            ;;
            
        macos)
            echo "Installing TA-Lib on macOS..."
            # Check if Homebrew is installed
            if ! command -v brew &> /dev/null; then
                echo "Homebrew not found. Installing Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            fi
            
            # Install TA-Lib
            brew install ta-lib
            
            # Install Python wrapper
            pip install ta-lib
            ;;
            
        windows)
            echo "For Windows, please download the appropriate wheel file from:"
            echo "https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib"
            echo "Then install it with:"
            echo "pip install <downloaded-wheel-file>"
            ;;
            
        *)
            echo "Unsupported OS. Please install TA-Lib manually."
            ;;
    esac
}

# Main execution
echo "TA-Lib Installation Helper"
echo "--------------------------"
install_talib

echo "Installation process completed." 