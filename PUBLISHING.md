# Publishing to PyPI Guide

This guide walks you through publishing your `colab-code-executor` package to PyPI.

## Prerequisites

1. **Create PyPI accounts:**
   - Production: https://pypi.org/account/register/
   - Test (recommended for first-time): https://test.pypi.org/account/register/

2. **Install build tools:**
   ```bash
   pip install --upgrade build twine
   ```

## Step 1: Customize Package Metadata

Edit `pyproject.toml` and update:
- `name`: Change to your desired package name (check availability on PyPI)
- `authors`: Add your name and email
- `maintainers`: Add maintainer info
- `project.urls`: Update with your GitHub repository URLs

## Step 2: Build the Package

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build source distribution and wheel
python -m build
```

This creates:
- `dist/colab-code-executor-0.1.0.tar.gz` (source distribution)
- `dist/colab-code-executor-0.1.0-py3-none-any.whl` (wheel)

## Step 3: Check the Package

```bash
# Verify package contents
tar -tzf dist/colab-code-executor-0.1.0.tar.gz

# Check package metadata and quality
twine check dist/*
```

## Step 4: Test Upload (Recommended)

Upload to TestPyPI first:

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# You'll be prompted for your TestPyPI username and password
# Or use API token (recommended)
```

Test installation:

```bash
# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ colab-code-executor

# Test the CLI
colab-code-executor --help
```

## Step 5: Upload to PyPI

Once tested, upload to production PyPI:

```bash
twine upload dist/*
```

## Using API Tokens (Recommended)

Instead of username/password, use API tokens:

1. **Get API token:**
   - PyPI: https://pypi.org/manage/account/token/
   - TestPyPI: https://test.pypi.org/manage/account/token/

2. **Configure `.pypirc`:**
   ```bash
   # Create ~/.pypirc
   cat > ~/.pypirc <<EOF
   [distutils]
   index-servers =
       pypi
       testpypi

   [pypi]
   username = __token__
   password = pypi-YOUR-API-TOKEN-HERE

   [testpypi]
   username = __token__
   password = pypi-YOUR-TESTPYPI-TOKEN-HERE
   EOF

   # Secure the file
   chmod 600 ~/.pypirc
   ```

3. **Upload without prompts:**
   ```bash
   twine upload --repository testpypi dist/*
   twine upload dist/*
   ```

## Version Management

When releasing new versions:

1. Update version in `pyproject.toml`
2. Update `__version__` in `src/colab_code_executor/__init__.py`
3. Create git tag:
   ```bash
   git tag -a v0.1.0 -m "Release version 0.1.0"
   git push origin v0.1.0
   ```
4. Rebuild and upload

## Automated Publishing with GitHub Actions

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    - name: Build package
      run: python -m build
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

Store your PyPI API token in GitHub Secrets as `PYPI_API_TOKEN`.

## Verification

After publishing, verify your package:

```bash
# Install from PyPI
pip install colab-code-executor

# Test the CLI
colab-code-executor --version
colab-code-executor --help

# Test programmatic usage
python -c "from colab_code_executor import Settings, JupyterClient; print('OK')"
```

## Troubleshooting

**Package name already exists:**
- Choose a different name in `pyproject.toml`
- Check availability: https://pypi.org/search/?q=your-package-name

**Upload fails with 403:**
- Verify API token is correct
- Check token has upload permissions

**Import errors after install:**
- Verify package structure: `pip show -f colab-code-executor`
- Check `src/colab_code_executor/__init__.py` imports

**Missing dependencies:**
- Ensure all dependencies are listed in `pyproject.toml`
- Test in clean virtual environment

## Resources

- PyPI packaging guide: https://packaging.python.org/
- Twine documentation: https://twine.readthedocs.io/
- PEP 517/518: Modern Python packaging standards
