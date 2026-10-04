# CI Regression Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a GitHub Actions workflow for regression testing across Python 3.10-3.12, lint checks with Ruff, and secret leakage prevention.

**Architecture:** A GitHub Actions workflow (`.github/workflows/ci.yml`) runs on push and pull_request. A matrix job tests against Python 3.10, 3.11, and 3.12 using pytest. A lint job verifies code quality using ruff. A secret check ensures `.env` and `auth.json` are never committed.

---

### Task 1: Create GitHub Actions Workflow & Ruff Configuration

**Files:**
- Create: `.github/workflows/ci.yml`
- Test: Local lint and pytest run

- [ ] **Step 1: Test Ruff locally to ensure zero current lint errors**
- [ ] **Step 2: Create `.github/workflows/ci.yml`**
- [ ] **Step 3: Commit and push to GitHub**
- [ ] **Step 4: Verify CI run status on GitHub**
