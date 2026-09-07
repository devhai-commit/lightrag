---
description: Run code quality checks on a directory
allowed-tools: Read, Glob, Grep, Bash(npm:*), Bash(pytest:*), Bash(ruff:*)
---

# Code Quality Review

Review code quality in: $ARGUMENTS

## Instructions

1. **Identify files to review**:
   - Backend (`micco-backend/backend`): `.py` files, exclude tests/migrations
   - Frontend (`micco-frontend/src`): `.jsx`/`.js` files, exclude generated files

2. **Run automated checks**:
   ```bash
   # Frontend
   cd micco-frontend && npm run lint
   # Backend
   cd micco-backend/backend && pytest tests/ -x --tb=short
   ```

3. **Manual review checklist**:
   - Type hints on backend async functions, Pydantic v2 schemas for all endpoints
   - Proper error handling (no silent `except: pass`)
   - Loading states handled correctly (frontend)
   - Empty states for lists (frontend)
   - Buttons disabled during async operations (frontend)

4. **Report findings** organized by severity:
   - Critical (must fix)
   - Warning (should fix)
   - Suggestion (could improve)
