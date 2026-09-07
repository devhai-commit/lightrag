---
description: QA Testing skill - chạy tests và đảm bảo chất lượng 95%
---

## QA Tester Skill

Chạy tests và đảm bảo chất lượng đạt 95% trước khi bàn giao.

### Workflow
```
1. Run backend tests
2. Run frontend tests
3. Analyze failures
4. Report → Fix → Re-test
5. Loop đến khi 95% pass
```

### Commands

#### Backend Tests
```bash
cd micco-backend/backend && pytest tests/ -v --tb=short
```

#### Frontend Tests
Chưa có test runner cấu hình cho frontend (không có Jest/Vitest). Dùng `/e2e-test` để kiểm thử
qua trình duyệt thay vì `npm run test`.

#### Full QA Pipeline
```bash
# 1. Backend
cd micco-backend/backend && pytest tests/ -v

# 2. Frontend (chưa có test runner — dùng /e2e-test)

# 3. RAG Pipeline
cd micco-backend/backend && pytest tests/integration/test_rag_pipeline.py -v
```

### Quality Criteria
| Metric | Target |
|--------|--------|
| Test Pass Rate | ≥ 95% |
| Coverage | ≥ 80% |
| Critical Bugs | 0 |

### Report Template
```markdown
## QA Report

### Summary
- Tests: XX/XX passed (XX%)
- Coverage: XX%
- Status: ✅ PASS / ❌ FAIL

### Failures
| Test | Error | Fix |
|------|-------|-----|
| ... | ... | ... |

### Next Steps
...
```
