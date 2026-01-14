#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "Starting Chrome setup..."

# Update package list
echo "Updating package list..."
sudo apt-get update

# Install basic tools
echo "Installing basic tools..."
sudo apt-get install -y wget curl unzip gnupg2

# Install comprehensive list of dependencies for Chrome and Chromedriver
# This list covers almost all potential missing libraries on minimal Debian/Ubuntu systems
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

# Add Google Chrome repository key
echo "Adding Google Chrome key..."
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -

# Add Google Chrome repository
echo "Adding Google Chrome repository..."
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Update package list again
echo "Updating package list (2)..."
sudo apt-get update

# Install Google Chrome
echo "Installing Google Chrome Stable..."
sudo apt-get install -y google-chrome-stable

# Verify Installation
echo "Verifying installation..."
if command -v google-chrome &> /dev/null; then
    CHROME_VERSION=$(google-chrome --version)
    echo "✓ Google Chrome found: $CHROME_VERSION"
else
    echo "❌ ERROR: google-chrome command not found!"
    exit 1
fi

echo "Setup completed successfully!"
