#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "Starting Chrome setup..."

# 1. Clean up potential broken previous attempts first
# This prevents "apt-get update" from failing due to the bad signature we just encountered
if [ -f /etc/apt/sources.list.d/google-chrome.list ]; then
    echo "Removing previous Google Chrome source list..."
    sudo rm -f /etc/apt/sources.list.d/google-chrome.list
fi

# 2. Update package list (should work now that bad repo is gone)
echo "Updating package list..."
sudo apt-get update

# 3. Install basic tools and GPG
echo "Installing basic tools..."
sudo apt-get install -y wget curl unzip gnupg2

# 4. Install system dependencies for Chrome
echo "Installing system dependencies..."
sudo apt-get install -y \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    wget \
    xdg-utils \
    libxshmfence1

# 5. Install Google Chrome Signing Key (Modern "signed-by" method)
# This fixes the "OpenPGP signature verification failed" error
echo "Installing Google Chrome key..."
sudo mkdir -p /usr/share/keyrings
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor | sudo tee /usr/share/keyrings/google-chrome.gpg > /dev/null

# 6. Add Google Chrome repository with explicit key reference
echo "Adding Google Chrome repository..."
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# 7. Update package list again to pick up the new repo
echo "Updating package list (2)..."
sudo apt-get update

# 8. Install Google Chrome
echo "Installing Google Chrome Stable..."
sudo apt-get install -y google-chrome-stable

# 9. Verify Installation
echo "Verifying installation..."
if command -v google-chrome &> /dev/null; then
    CHROME_VERSION=$(google-chrome --version)
    echo "✓ Google Chrome found: $CHROME_VERSION"
else
    echo "❌ ERROR: google-chrome command not found!"
    exit 1
fi

echo "Setup completed successfully!"
