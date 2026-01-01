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
Interactive script for building and publishing the package to PyPI or TestPyPI.

**Usage:**
```bash
./scripts/publish.sh
```

**Features:**
- Automatic cleanup of old builds
- Package building (wheel + source dist)
- Package quality checks with `twine`
- Interactive upload selection (TestPyPI/PyPI/Skip)

**Steps:**
1. Cleans previous builds
2. Builds source distribution and wheel
3. Validates with `twine check`
4. Prompts for upload destination
5. Uploads to selected repository

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
Quick start script for the colab-code-executor server.

**Usage:**
```bash
./scripts/quickstart.sh
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
# 1. Build the package
./scripts/publish.sh
# Select option 3 (Skip upload)

# 2. Get API token from TestPyPI
# Visit: https://test.pypi.org/manage/account/token/

# 3. Upload with token
export TESTPYPI_TOKEN='pypi-YOUR-TOKEN'
./scripts/upload_with_token.sh

# 4. Test installation
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple \
    colab-code-executor
```

### Publish to Production PyPI
```bash
# 1. Build package
./scripts/publish.sh
# Select option 2 (PyPI)

# Or use token authentication:
export PYPI_TOKEN='pypi-YOUR-PRODUCTION-TOKEN'
twine upload dist/* -u __token__ -p "$PYPI_TOKEN"
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
