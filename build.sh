#!/usr/bin/env bash
# Install ffmpeg
apt-get update && apt-get install -y ffmpeg
# Install Python dependencies
pip install -r requirements.txt
