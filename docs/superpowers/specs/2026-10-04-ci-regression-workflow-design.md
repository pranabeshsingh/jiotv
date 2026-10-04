# CI Regression Testing & Quality Checks Design Specification

**Date:** 2026-10-04  
**Target Repository:** `git@github.com:pranabeshsingh/jiotv.git`  
**Purpose:** Implement automated continuous integration (CI) workflows using GitHub Actions for regression testing, linting, and secret leakage prevention.

---

## 1. Requirements & Goals

1. **Regression Testing**:
   - Execute the test suite using `pytest -v` across supported Python versions (`3.10`, `3.11`, `3.12`) on `ubuntu-latest`.
   - Ensure all modules (`app.config`, `app.jio_api`, `app.channel_manager`, `app.routes.iptv`, `app.routes.api`, `app.routes.web`, `scripts.migrate_credentials`) pass without regressions.
2. **Linting & Code Standards**:
   - Run `ruff check .` to catch syntax errors, undefined names, unused imports, and common anti-patterns without slowing down CI runs.
3. **Secret Leak Prevention**:
   - Run an automated file check verifying that `.env`, `data/auth.json`, or real phone numbers are never committed to git.
4. **Triggers**:
   - Run on `push` to `main` branch.
   - Run on `pull_request` targeting `main`.

---

## 2. File Architecture

- `.github/workflows/ci.yml`: Primary workflow file containing matrix testing, linting, and sanity checks.
- `pyproject.toml` or `requirements.txt`: Configuration or dev requirements (e.g. `ruff`).

---

## 3. Workflow Steps

```yaml
name: CI & Regression Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check .

  test:
    needs: lint
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Run regression tests
        run: |
          pytest -v

  secret-sanity-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify no tracked secrets
        run: |
          if git ls-files | grep -E '^\.env$|^data/auth\.json$|^data/settings\.json$'; then
            echo "Error: Tracked secret file detected!"
            exit 1
          fi
          echo "Secret check passed: No secret files tracked."
```

---

## 4. Verification

- Push workflow to GitHub and verify that GitHub Actions starts and runs tests successfully across Python 3.10, 3.11, and 3.12.
