## Pipeline: Profile API latency, optimize the slowest endpoints, and validate the improvements

### Steps

| Step | Role | Task Summary | Depends On |
|------|------|-------------|-----------|
| S1 | researcher | Profile all API endpoints in the factory codebase: identify HTTP/CLI entry points, measure or estimate latency for each code path, identify the top 3 slowest endpoints/operations, and research optimization techniques applicable to each bottleneck (e.g., async batching, caching, subprocess pooling, lazy imports). Document findings with measurable latency data per endpoint. | - |
| S2 | evaluator | Run baseline eval (`python eval/score.py`) and capture current composite scores. Additionally, run the smoke test (`pytest tests/ -x -q --tb=short`) to establish a green baseline. Record all latency-relevant metrics and current test pass/fail state. | - |
| S3 | strategist | Using the researcher's latency profile (S1) and the evaluator's baseline scores (S2), rank the identified bottlenecks by expected impact. Produce one concrete optimization hypothesis per slow endpoint, prioritized by estimated latency reduction. Each hypothesis must specify: the endpoint, the root cause of slowness, the proposed fix, and the expected improvement. | S1, S2 |
| S4 | builder | Implement the #1 highest-priority optimization from the strategist's ranked list (S3). Work on a feature branch. Ensure changes include benchmarks or timing instrumentation to prove the improvement. Run `ruff check .` and the smoke test before finishing. | S3 |
| S5 | reviewer | Review the optimization from S4: verify correctness (no logic regressions), confirm benchmarks are included, check that no guard violations occur (no deleted tests, no out-of-scope changes), and validate that the code follows project style (snake_case, 100 char lines, strict Pydantic models). | S4 |
| S6 | evaluator | Run post-optimization eval (`python eval/score.py`) and the smoke test. Compare latency metrics and composite scores against the S2 baseline. Report whether latency improved or regressed, and by how much. | S5 |
| S7 | builder | If S6 shows improvement (no regression): implement the #2 optimization from the strategist's list (S3). Same standards as S4 -- feature branch, benchmarks, lint clean, smoke test passing. If S6 shows regression: skip this step entirely. | S6 |
| S8 | archivist | Archive the full pipeline results to `.factory/archive/`: the performance profile from S1, all optimizations attempted, before/after latency metrics from S2 and S6, reviewer verdicts, and a summary of net improvement. Include the strategist's prioritized list and note which items remain unaddressed for future cycles. | S7 |

### Gate Rules

- **After S1:** PROCEED if hot paths are identified with measurable latency data for at least 2 endpoints; REDIRECT if the research is too shallow (no specific latency numbers or only vague observations) -- re-invoke with a narrower focus on timing instrumentation; ABORT if no API endpoints or latency-relevant code paths exist in the project.
- **After S2:** PROCEED if baseline eval runs successfully and produces valid JSON scores; REDIRECT if eval command fails due to fixable configuration -- re-invoke after checking `eval_profile.json`; ABORT if eval infrastructure is fundamentally broken.
- **After S3:** PROCEED if hypotheses are specific (one per endpoint), include expected latency reduction estimates, and are scoped to individual PRs; REDIRECT if hypotheses are too broad or lack measurable targets; ABORT if no actionable optimizations can be identified.
- **After S5:** PROCEED if the reviewer passes the optimization with no correctness issues; REDIRECT if the reviewer identifies minor fixable issues (re-invoke builder with corrections, max 2 retries); ABORT if the reviewer finds fundamental correctness problems or guard violations (revert S4 changes).
- **After S6:** PROCEED if latency improved and composite score did not regress below the 0.8 threshold; ABORT if latency regressed or composite score dropped below threshold (revert S4 changes and skip S7).
- **After S7:** Apply the same gate pattern as S5-S6: the #2 optimization should be reviewed and eval'd before archival. If S7 was skipped (due to S6 regression), proceed directly to S8 with a note that only archival of the failed attempt is needed.

### Parallelism

- **S1 and S2** run in parallel (both have no dependencies).
- All other steps are sequential due to data dependencies.
- **S7 is conditional** -- it is skipped entirely if S6 indicates a regression.

### Error Recovery

- Agent timeout on any step: retry once with a narrower scope (e.g., reduce from top 3 to top 1 endpoint).
- Agent failure: read `.factory/reviews/<role>-latest.md`, decide REDIRECT (fixable) or ABORT (fundamental).
- 2 consecutive failures on the same step: ABORT the pipeline and proceed to archival (S8) with partial results.
