# Backend test baseline

Recorded on 2026-08-27 from branch `chore/production-baseline`, before production
baseline changes.

## Host run

Command:

```text
cd backend
python -m unittest discover -s tests -p "test_*.py" -v
```

Environment: Python 3.12.10. Result: **failed before the suite could run**.
Discovery reported 19 entries: 1 passed and 18 import errors. The host Python
environment did not have project dependencies installed (`fastapi`, `sqlalchemy`,
`pydantic`, `httpx`, and `python-docx` were among the missing packages).

This is an environment baseline, not evidence of application test failures. The CI
workflow installs pinned application dependencies and runs the complete suite,
including the PostgreSQL/pgvector integration tests.

## Verification after baseline changes

- Ruff: passed.
- Backend unit tests: **141 passed** in 38.114 seconds.
- PostgreSQL/pgvector integration tests: delegated to CI; the local Docker daemon
  was unavailable.
- Production Compose interpolation and schema: passed with non-sample test secrets.
