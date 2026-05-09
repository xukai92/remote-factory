## Pipeline: Fix all lint warnings in this project

### Project State

- **Project:** `/workspace/home/kai/src/remote-factory`
- **Detected state:** `has_factory`
- **Lint tools:** `ruff check .` (default rules, 100-char line length), `mypy factory/`
- **Current status:** Both `ruff check .` and `mypy factory/` report zero warnings/errors under the project's configured rule set. The project is already lint-clean.

### Steps

| Step | Role       | Task Summary                                                                                                                                                                                                                                           | Depends On |
|------|------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------|
| S1   | evaluator  | Run `ruff check .` and `mypy factory/` against the project. Capture full output including warning counts, rule codes, file locations, and severity. Report whether any warnings exist and, if so, categorize them by rule code and file.                | -          |
| S2   | builder    | For every warning reported in S1, fix the underlying code. Group fixes by file to minimize churn. After all fixes, run `ruff check .` and `mypy factory/` to verify zero warnings remain. Also run `pytest tests/ -x -q --tb=short` as a smoke test to confirm no regressions. Commit fixes on a feature branch. | S1         |
| S3   | archivist  | Archive the results: number of warnings found in S1, list of rule codes encountered, files modified in S2, final lint/type-check status, and whether the smoke test passed. Write to `.factory/archive/`.                                              | S2         |

### Gate Rules

- **After S1:**
  - **PROCEED** if one or more warnings are found by either `ruff check .` or `mypy factory/` -- there is work for the builder to do.
  - **ABORT** if both tools report zero warnings -- the project is already lint-clean and no further steps are needed.
- **After S2:**
  - **PROCEED** if `ruff check .` and `mypy factory/` both exit cleanly with zero warnings AND the smoke test (`pytest tests/ -x -q --tb=short`) passes.
  - **REDIRECT** if lint warnings remain (re-invoke builder with the residual warnings, max 2 retries).
  - **ABORT** if the smoke test fails after fixes, indicating regressions were introduced -- revert the branch and archive the failure.
- **After S3:**
  - No gate -- terminal step. Pipeline complete.

### Parallelism

No parallelism is needed. This is a strictly sequential pipeline: S1 -> S2 -> S3. Each step depends on the output of the previous one.

### Design Notes

- This pipeline follows the "Easy (2-3 steps)" reference template from the pipeline skill, adapted to also include `mypy` since the project uses both linters.
- The S1 gate is critical: given the current project state (zero warnings), this pipeline would ABORT immediately at S1, correctly recognizing there is nothing to fix.
- The builder step includes a smoke test gate beyond just re-running lint, because lint fixes (especially type annotation changes) can introduce runtime regressions.
- If the goal were expanded to include stricter rule sets (e.g., `ruff check . --select ALL`), S1's task description would need to be updated accordingly, and S2 would likely require multiple redirect cycles given the volume of additional rules.
