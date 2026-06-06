#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Download and install a static build of ffmpeg
echo "Downloading ffmpeg..."
curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | tar -xJ

# The extracted folder name varies by version, so we find it and move the binaries to /usr/local/bin 
# (Render does not allow writing to /usr/local/bin in native environment, so we move it to the project root or a bin folder in PATH)
mkdir -p bin
cp ffmpeg-*-static/ffmpeg bin/
cp ffmpeg-*-static/ffprobe bin/

echo "ffmpeg installation complete. Add './bin' to your PATH or Discord.py will find it if it's in the current directory."
