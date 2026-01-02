#!/bin/bash
# Install script for colab-code-executor package
set -e  # Exit on error

pip install colab-code-executor
npm install -g localtunnel
colab-code-executor --server-url http://192.168.10.10:8080 --port 8000 &
lt --port 8000 &
echo 1 > /content/code_executor
