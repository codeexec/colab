#!/bin/bash
# Publishing script for jupyter-kernel-proxy package

set -e  # Exit on error

echo "==================================="
echo "Colab Code Executor - Publishing"
echo "==================================="
echo ""

# Check if build and twine are installed
if ! command -v python &> /dev/null; then
    echo "Error: Python is not installed"
    exit 1
fi

echo "Checking for required tools..."
python -c "import build" 2>/dev/null || {
    echo "Installing build..."
    pip install --upgrade build
}

python -c "import twine" 2>/dev/null || {
    echo "Installing twine..."
    pip install --upgrade twine
}

# Clean previous builds
echo ""
echo "Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info src/*.egg-info

# Build the package
echo ""
echo "Building package..."
python -m build

# Check the package
echo ""
echo "Checking package quality..."
twine check dist/*

# Show what was built
echo ""
echo "Built files:"
ls -lh dist/

# Ask which repository to upload to
echo ""
echo "Select upload target:"
echo "1) TestPyPI (recommended for testing)"
echo "2) PyPI (production)"
echo "3) Skip upload (just build)"
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo ""
        echo "Uploading to TestPyPI..."
        twine upload --repository testpypi dist/*
        echo ""
        echo "Test installation with:"
        echo "pip install --index-url https://test.pypi.org/simple/ colab-code-executor"
        ;;
    2)
        echo ""
        read -p "Are you sure you want to upload to production PyPI? [y/N]: " confirm
        if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
            echo "Uploading to PyPI..."
            twine upload dist/*
            echo ""
            echo "Installation command:"
            echo "pip install colab-code-executor"
        else
            echo "Upload cancelled."
        fi
        ;;
    3)
        echo ""
        echo "Build completed. Upload skipped."
        ;;
    *)
        echo "Invalid choice. Upload skipped."
        ;;
esac

echo ""
echo "Done!"
