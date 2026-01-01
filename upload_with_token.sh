#!/bin/bash
# Upload to TestPyPI using API token

set -e

echo "========================================="
echo "Upload to TestPyPI with API Token"
echo "========================================="
echo ""
echo "Before running this script:"
echo "1. Get API token from: https://test.pypi.org/manage/account/token/"
echo "2. Set environment variable: export TESTPYPI_TOKEN='pypi-...'"
echo ""

# Check if token is set
if [ -z "$TESTPYPI_TOKEN" ]; then
    echo "ERROR: TESTPYPI_TOKEN environment variable not set"
    echo ""
    echo "Set it with:"
    echo "  export TESTPYPI_TOKEN='pypi-YOUR-TOKEN-HERE'"
    exit 1
fi

# Build if needed
if [ ! -d "dist" ]; then
    echo "Building package..."
    python -m build
fi

# Upload with token
echo "Uploading to TestPyPI..."
TWINE_USERNAME=__token__ TWINE_PASSWORD="$TESTPYPI_TOKEN" \
    twine upload --repository testpypi dist/*

echo ""
echo "✅ Upload successful!"
echo ""
echo "Test installation with:"
echo "  pip install --index-url https://test.pypi.org/simple/ jupyter-kernel-proxy"
