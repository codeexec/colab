#!/bin/bash
# Script to test local package installation

set -e

echo "========================================="
echo "Local Package Testing"
echo "========================================="
echo ""

# Check Python version
echo "1. Checking Python version..."
python --version
if [ $? -ne 0 ]; then
    echo "ERROR: Python not found"
    exit 1
fi
echo "✓ Python is available"
echo ""

# Install in editable mode
echo "2. Installing package in editable mode..."
pip install -e . --quiet
echo "✓ Package installed"
echo ""

# Test imports
echo "3. Testing Python imports..."
python -c "from colab_code_executor import Settings; print('  ✓ Settings imported')"
python -c "from colab_code_executor import StructuredLogger; print('  ✓ StructuredLogger imported')"
python -c "from colab_code_executor import JupyterClient; print('  ✓ JupyterClient imported')"
python -c "from colab_code_executor import KernelManager; print('  ✓ KernelManager imported')"
python -c "from colab_code_executor import app; print('  ✓ FastAPI app imported')"
python -c "import colab_code_executor; print(f'  ✓ Package version: {colab_code_executor.__version__}')"
echo ""

# Test CLI availability
echo "4. Testing CLI command..."
if command -v colab-code-executor &> /dev/null; then
    echo "✓ CLI command 'colab-code-executor' is available"
    colab-code-executor --version 2>&1 || true
else
    echo "⚠ CLI command not found in PATH"
    echo "  Try: pip install -e . --force-reinstall"
fi
echo ""

# Test CLI help
echo "5. Testing CLI help..."
colab-code-executor --help | head -n 5
echo "  ✓ CLI help works"
echo ""

# Check installed files
echo "6. Checking installed package files..."
python -c "import colab_code_executor; import os; print(f'  Package location: {os.path.dirname(colab_code_executor.__file__)}')"
echo ""

# List package contents
echo "7. Package contents:"
python << 'EOF'
import colab_code_executor
import os
import glob

pkg_dir = os.path.dirname(colab_code_executor.__file__)
files = glob.glob(os.path.join(pkg_dir, '*.py'))
for f in sorted(files):
    print(f"  - {os.path.basename(f)}")
EOF
echo ""

echo "========================================="
echo "✅ All basic tests passed!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Test the server: colab-code-executor --help"
echo "2. Run unit tests: pytest (if available)"
echo "3. Test with real Jupyter server"
echo ""
