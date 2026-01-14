#!/bin/bash

# Update package list
sudo apt-get update

# Install necessary dependencies
sudo apt-get install -y wget curl unzip gnupg2

# Add Google Chrome repository key
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -

# Add Google Chrome repository
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Update package list again
sudo apt-get update

# Install Google Chrome
sudo apt-get install -y google-chrome-stable

# Print installed version
google-chrome --version

echo "Google Chrome installation completed successfully!"
