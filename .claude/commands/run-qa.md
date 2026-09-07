---
description: Chạy QA tests và đảm bảo chất lượng đạt 95%
---

## QA Testing Workflow

### Quy trình test nhiều lần đạt 95% quality:

#### Lần 1: Initial Test
```bash
# Backend tests
cd micco-backend/backend && pytest tests/ -v --tb=short

# Frontend: chưa có test runner cấu hình — dùng /e2e-test qua trình duyệt
```

#### Lần 2: Integration Test
```bash
# Backend integration
cd micco-backend/backend && pytest tests/integration/ -v

# Check API endpoints
curl -s http://localhost:8000/api/v1/health
```

#### Lần 3: RAG Pipeline Test
```bash
# Full RAG pipeline
cd micco-backend/backend && pytest tests/integration/test_rag_pipeline.py -v
```

#### Lần N: Fix & Retest
- Nếu có failures → analyze và fix
- Retest cho đến khi đạt 95% pass rate

### Quality Criteria
```
✅ PASS = Test pass rate ≥ 95%
❌ FAIL = Test pass rate < 95%
```

### Report Format
```markdown
## QA Report - Iteration [N]

### Results
- Total: XX
- Passed: XX (XX%)
- Failed: XX

### Failed Tests
1. test_xxx - [reason] → Fixed by [agent]

### Status
[ ] Continue iteration
[x] Quality gate PASSED
```

## Quick Commands

### Single command - Run backend tests
```bash
cd micco-backend/backend && pytest tests/ -v --tb=line
```
Frontend chưa có test runner — dùng `/e2e-test` sau khi backend pass.

### With coverage
```bash
cd micco-backend/backend && pytest tests/ --cov=app --cov-report=term-missing
```
