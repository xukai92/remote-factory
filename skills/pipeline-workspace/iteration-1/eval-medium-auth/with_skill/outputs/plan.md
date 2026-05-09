## Pipeline: Research the authentication timeout bug and fix it

### Steps

| Step | Role | Task Summary | Depends On |
|------|------|-------------|-----------|
| S1 | researcher | Research the authentication timeout bug: read auth middleware and session/token handling code, search for timeout-related configuration and error paths, check logs and issues for timeout symptoms, and identify the root cause. | - |
| S2 | evaluator | Run baseline eval (`python eval/score.py`) to capture current project scores before any changes. | - |
| S3 | strategist | Given the researcher's root-cause analysis (S1) and the baseline scores (S2), generate fix hypotheses ranked by likelihood of resolving the timeout. Pick the single most targeted fix — it should be scoped to one PR. | S1, S2 |
| S4 | builder | Implement the top hypothesis from S3 on a feature branch. Include a regression test that reproduces the timeout condition and verifies the fix. Open a PR. | S3 |
| S5 | reviewer | Review the PR from S4: verify correctness of the timeout fix, confirm no regressions introduced, check that the new test covers the failure mode, and ensure scope is limited to the auth timeout issue. | S4 |
| S6 | archivist | Archive the pipeline results: document the root cause of the authentication timeout, the fix approach chosen, the reviewer verdict, and the before/after eval comparison. | S5 |

### Gate Rules

- **After S1:** PROCEED if a specific root cause (or strong candidate) for the authentication timeout is identified with supporting evidence (code references, log traces, or reproduction steps). REDIRECT if the research is too shallow — re-invoke the researcher with a narrower scope (e.g., focus on token expiry logic or session middleware specifically). ABORT if the researcher determines there is no authentication timeout bug (false report).
- **After S3:** PROCEED if the top hypothesis is specific, actionable, and scoped to a single PR-sized change. REDIRECT if hypotheses are too vague or too broad — ask the strategist to narrow down using the researcher's evidence. ABORT if no viable hypothesis can be formed from the research.
- **After S5:** PROCEED if the reviewer passes the PR with no correctness issues or guard violations. REDIRECT if the reviewer identifies minor issues — send back to the builder for a second attempt (max 1 redirect). ABORT if the reviewer finds fundamental correctness problems or guard violations that indicate the hypothesis was wrong.

### Parallelism

S1 (researcher) and S2 (evaluator) run in parallel as the first batch — neither depends on the other. All subsequent steps are sequential: S3 depends on both S1 and S2; S4 depends on S3; S5 depends on S4; S6 depends on S5.

### Error Recovery

- If any agent times out, retry once with a shorter task scope.
- If any agent fails, read its output from `.factory/reviews/<role>-latest.md`, diagnose the failure, and decide REDIRECT (re-invoke with corrections) or ABORT (skip downstream steps and jump to archival summary).
- After 2 consecutive failures on the same step, ABORT the pipeline and archive what was learned.
