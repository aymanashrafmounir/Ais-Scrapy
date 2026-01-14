#!/bin/bash

# Update package list
sudo apt-get update

# Install basic tools
sudo apt-get install -y wget curl unzip gnupg2

# Install dependencies often missing in minimal environments for Chrome/Chromedriver
# These resolve the "Status code was: 127" (missing shared libraries) error
sudo apt-get install -y \
    libxss1 \
    libappindicator3-1 \
    libasound2 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxtst6 \
    lsb-release \
    xdg-utils \
    libgbm1 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libxshmfence1 \
    ca-certificates \
    fonts-liberation

# Add Google Chrome repository key
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -

# Add Google Chrome repository
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Update package list again
sudo apt-get update

# Install Google Chrome
sudo apt-get install -y google-chrome-stable

# Print installed version to verify
echo "Verifying Google Chrome installation..."
if command -v google-chrome &> /dev/null; then
    google-chrome --version
else
    echo "ERROR: google-chrome command not found!"
fi

echo "Google Chrome installation completed successfully!"
