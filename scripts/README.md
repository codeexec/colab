# Scripts Directory

This directory contains utility scripts for building, testing, and publishing the `colab-code-executor` package.

## Available Scripts

### 🧪 Testing

#### `test_local_install.sh`
Comprehensive local testing script that verifies package installation and functionality.

**Usage:**
```bash
./scripts/test_local_install.sh
```

**What it tests:**
- Python version compatibility
- Package installation
- Python imports (all modules)
- CLI command availability
- Package version
- Installed files and structure

---

### 📦 Publishing

#### `publish.sh`
Interactive script for testing, building, and publishing the package to PyPI or TestPyPI.

**Usage:**
```bash
./scripts/publish.sh           # Run with tests (default)
./scripts/publish.sh --no-test # Skip tests
```

**Features:**
- **Automated testing** (unit + integration tests)
- Automatic cleanup of old builds
- Package building (wheel + source dist)
- Package quality checks with `twine`
- Interactive upload selection (TestPyPI/PyPI/Skip)

**Steps:**
1. Installs dev dependencies (pytest, requests, etc.)
2. Runs unit tests with pytest (`test_server.py`)
3. Runs integration tests (`test_lro.py`):
   - Starts server in background
   - Runs test suite
   - Stops server
4. Cleans previous builds
5. Builds source distribution and wheel
6. Validates with `twine check`
7. Prompts for upload destination
8. Uploads to selected repository

**Testing Requirements:**
- Tests require a running Jupyter server at `$JUPYTER_SERVER_URL` (default: http://127.0.0.1:8080)
- Set `JUPYTER_TOKEN` if your Jupyter server requires authentication
- Use `--no-test` flag to skip tests if needed

**Environment Variables:**
```bash
export JUPYTER_SERVER_URL="http://localhost:8080"  # Optional
export JUPYTER_TOKEN="your-token"                   # Optional
```

---

#### `upload_with_token.sh`
Simplified upload script using API token authentication.

**Usage:**
```bash
# Set your TestPyPI token
export TESTPYPI_TOKEN='pypi-YOUR-TOKEN-HERE'

# Run upload
./scripts/upload_with_token.sh
```

**Prerequisites:**
- Get API token from https://test.pypi.org/manage/account/token/
- Set `TESTPYPI_TOKEN` environment variable

**What it does:**
- Validates token is set
- Builds package if needed
- Uploads to TestPyPI using token authentication

---

### 🚀 Quick Start

#### `quickstart.sh`
Interactive demonstration of the Long-Running Operations (LRO) pattern with the colab-code-executor server.

**Usage:**
```bash
# Ensure server is running first
colab-code-executor &

# Run the quick start demo
./scripts/quickstart.sh
```

**What it demonstrates:**
1. **Health Check**: Verifies server is running
2. **Start Kernel**: Creates a new Jupyter kernel
3. **Execute Code**: Submits code for non-blocking execution
4. **Poll Status**: Monitors execution progress in real-time
5. **Display Results**: Shows output, return values, and execution duration
6. **Cleanup**: Shuts down the kernel

**Features:**
- Self-contained (no external dependencies)
- Demonstrates the LRO pattern with a 6-second computation
- Shows both stdout output and return values
- Visual progress indicators with emojis
- Error handling for failed executions
- Automatic kernel cleanup

**Example Output:**
```
==========================================
Colab Code Executor - Quick Start
==========================================
Server URL: http://127.0.0.1:8000

✓ Server is healthy

1️⃣  Starting kernel...
   ✓ Kernel started: abc-123

2️⃣  Submitting code for execution (non-blocking)...
   ✓ Execution submitted: xyz-789
   ℹ️  Code is running in background (non-blocking)

3️⃣  Polling for execution status...
   Poll #1: Status = RUNNING
   Poll #2: Status = RUNNING
   ...
   Poll #7: Status = COMPLETED
   ✓ Execution completed successfully!

4️⃣  Displaying results...

📊 EXECUTION SUMMARY
============================================================
Execution ID: xyz-789
Kernel ID: abc-123
Status: COMPLETED
Duration: 6.123 seconds

📤 OUTPUT
------------------------------------------------------------
=== Long-Running Computation Demo ===

Generating random data...
Data: [0.123 0.456 ...]

Processing in steps:
  Step 1/5 completed
  ...

📊 RETURN VALUE:
{'mean': 0.456, 'std': 0.234, ...}
------------------------------------------------------------

5️⃣  Cleaning up...
   ✓ Kernel shutdown: abc-123

==========================================
✅ Quick Start Complete!
==========================================
```

---

## Common Workflows

### First-Time Setup and Test
```bash
# 1. Install in development mode
pip install -e .

# 2. Run comprehensive tests
./scripts/test_local_install.sh

# 3. Verify CLI works
colab-code-executor --help
```

### Build and Publish to TestPyPI
```bash
# 1. Ensure Jupyter server is running (for integration tests)
jupyter lab --port 8080 &

# 2. Run tests and build the package
./scripts/publish.sh
# - Unit tests will run automatically
# - Integration tests will run automatically
# - Select option 1 (TestPyPI) or 3 (Skip upload)

# 3. Test installation
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple \
    colab-code-executor
```

### Publish to Production PyPI
```bash
# 1. Ensure Jupyter server is running
jupyter lab --port 8080 &

# 2. Run tests and build package
./scripts/publish.sh
# - All tests will run before building
# - Select option 2 (PyPI)

# Or skip tests if already validated:
./scripts/publish.sh --no-test
# Select option 2 (PyPI)
```

## Script Permissions

All scripts should be executable. If needed, run:
```bash
chmod +x scripts/*.sh
```

## Requirements

Scripts require the following tools:
- `python` (3.10+)
- `pip`
- `build` package: `pip install build`
- `twine` package: `pip install twine`

## Troubleshooting

**Script not executable:**
```bash
chmod +x scripts/script_name.sh
```

**Build tools missing:**
```bash
pip install --upgrade build twine
```

**Token authentication fails:**
- Verify token starts with `pypi-`
- Check token has correct permissions
- Ensure environment variable is set correctly

## Development

When creating new scripts:
1. Add them to this `scripts/` directory
2. Make them executable: `chmod +x scripts/new_script.sh`
3. Update this README
4. Use clear naming conventions
5. Add usage instructions as comments in the script
