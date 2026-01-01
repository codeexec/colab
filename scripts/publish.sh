#!/bin/bash
# Publishing script for colab-code-executor package
#
# Usage:
#   ./publish.sh           # Run with tests (default)
#   ./publish.sh --no-test # Skip tests

set -e  # Exit on error

# Parse command line arguments
SKIP_TESTS=0
if [[ "$1" == "--no-test" ]]; then
    SKIP_TESTS=1
    echo "⚠️  WARNING: Tests will be skipped!"
    echo ""
fi

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

# Install dev dependencies for testing
echo ""
echo "Installing dev dependencies..."
pip install -q "pytest>=7.0.0" "pytest-asyncio>=0.21.0" "pytest-mock>=3.10.0" "pytest-cov>=4.0.0" "requests>=2.28.0"

# Install package in development mode for testing
echo "Installing package in development mode..."
pip install -q -e .

# =========================
# Run Tests
# =========================

if [ $SKIP_TESTS -eq 0 ]; then
    echo ""
    echo "==================================="
    echo "Running Tests"
    echo "==================================="

    # Run unit tests with pytest
    echo ""
    echo "1. Running unit tests (pytest)..."
    cd src/colab_code_executor
    if pytest test_server.py -v --tb=short; then
        echo "✓ Unit tests passed!"
    else
        echo "✗ Unit tests failed!"
        cd ../..
        exit 1
    fi
    cd ../..

    # Run integration tests (test_lro.py)
    echo ""
    echo "2. Running integration tests (test_lro.py)..."
    echo "   Starting server in background..."

    # Set environment variables for test Jupyter server (override any existing values)
    export JUPYTER_SERVER_URL="http://127.0.0.1:8080"
    export JUPYTER_TOKEN=""

    # Start the server in background
    python -m uvicorn colab_code_executor.server:app --host 0.0.0.0 --port 8000 > /tmp/server.log 2>&1 &
    SERVER_PID=$!

    # Wait for server to start
    echo "   Waiting for server to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            echo "   ✓ Server is ready!"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "   ✗ Server failed to start!"
            kill $SERVER_PID 2>/dev/null || true
            cat /tmp/server.log
            exit 1
        fi
        sleep 1
    done

    # Run the integration test
    echo "   Running test_lro.py..."
    if python src/colab_code_executor/test_lro.py; then
        echo "   ✓ Integration tests passed!"
        TEST_RESULT=0
    else
        echo "   ✗ Integration tests failed!"
        TEST_RESULT=1
    fi

    # Stop the server
    echo "   Stopping server..."
    kill $SERVER_PID 2>/dev/null || true
    wait $SERVER_PID 2>/dev/null || true

    # Exit if integration tests failed
    if [ $TEST_RESULT -ne 0 ]; then
        echo ""
        echo "Tests failed! Fix the issues before publishing."
        exit 1
    fi

    echo ""
    echo "✓ All tests passed!"
else
    echo ""
    echo "⚠️  Skipping tests (--no-test flag used)"
fi

# =========================
# Build Package
# =========================

# Clean previous builds
echo ""
echo "==================================="
echo "Building Package"
echo "==================================="
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
echo "==================================="
echo "Publishing Complete!"
echo "==================================="
if [ $SKIP_TESTS -eq 0 ]; then
    echo "✓ Unit tests passed"
    echo "✓ Integration tests passed"
else
    echo "⚠️  Tests were skipped"
fi
echo "✓ Package built and checked"
echo ""
echo "Done!"
