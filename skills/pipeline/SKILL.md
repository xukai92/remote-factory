---
name: pipeline
description: "Design and execute a custom multi-agent pipeline for any goal. Analyzes the goal, selects appropriate specialist agents, designs a DAG of steps with dependencies, and executes them via factory CLI with gate decisions between steps. Use when the user says 'run a pipeline for X', 'orchestrate X', or wants a custom multi-agent workflow."
disable-model-invocation: true
argument-hint: "<goal>"
---

# Pipeline — Dynamic Multi-Agent Orchestrator

You design and execute custom multi-agent pipelines to accomplish the user's goal.

The user wants: **$ARGUMENTS**

## Prerequisites

The `factory` CLI must be installed:

```bash
command -v factory >/dev/null 2>&1 || uv tool install "${CLAUDE_PLUGIN_ROOT}"
mkdir -p .factory/pipeline
```

## Your Agents

Spawn specialists via the CLI. Each agent gets a fresh context window.

```bash
factory agent <role> --task "<task description>" --project "$(pwd)" [--timeout N]
```

| Role | Purpose |
|------|---------|
| researcher | Web research, codebase analysis, domain studies |
| strategist | Generate prioritized hypotheses from observations |
| builder | Implement code changes on a feature branch, open PRs |
| reviewer | Review PRs, guard checks, keep/revert verdicts |
| evaluator | Run evals, compare before/after scores |
| archivist | Record findings to `.factory/archive/` |
| distiller | Refine vague ideas into buildable specs |

### Invocation Rules

Each `factory agent` call is synchronous and blocking — it returns only when the agent finishes. Do not shell-background (`&`) individual commands.

To run steps in parallel, issue multiple `factory agent` commands as **separate bash tool calls in the same message turn**. Claude Code executes them concurrently. This is parallel tool calls, not shell backgrounding.

The runner captures agent stdout to `.factory/reviews/<role>-latest.md`.

## Phase 1: Design the Pipeline

1. **Understand the goal** — what outcome is desired? Which agents are needed?
2. **Inspect project state:**
   ```bash
   factory detect "$(pwd)"
   cat .factory/config.json 2>/dev/null
   ```
3. **Write the pipeline plan** to `.factory/pipeline/plan.md`:

```markdown
## Pipeline: <goal summary>

### Steps

| Step | Role | Task Summary | Depends On |
|------|------|-------------|-----------|
| S1 | researcher | ... | - |
| S2 | evaluator | ... | - |
| S3 | strategist | ... | S1, S2 |
| ... | ... | ... | ... |

### Gate Rules
- After S1: PROCEED if ...; REDIRECT if ...
- After S3: PROCEED if ...; ABORT if ...
```

### Design Principles

- **Minimize invocations** — only agents needed for this goal
- **Maximize parallelism** — steps whose dependencies are all satisfied and that don't depend on each other can be issued as parallel tool calls
- **Mandatory archival** — always include at least one archivist step at the end
- **Gate rules** — define PROCEED/REDIRECT/ABORT criteria for critical transitions

## Phase 2: Execute the Pipeline

Process steps in topological order:

1. **Identify next batch** — steps whose dependencies are all complete
2. **Build task strings** — incorporate output from prior steps by reading `.factory/reviews/<role>-latest.md`
3. **Invoke agents** — single or parallel batch
4. **Read output** — `cat .factory/reviews/<role>-latest.md`
5. **Apply gate rule:**
   - **PROCEED**: Move to next step
   - **REDIRECT**: Re-invoke with corrections (max 2 per step)
   - **ABORT**: Skip downstream steps, jump to summary
6. **Repeat** until done

### Error Recovery

- Agent timeout: retry once with shorter scope
- Agent failure: check output, decide REDIRECT or ABORT
- 2 consecutive failures: ABORT pipeline

### Final Summary

Write `.factory/pipeline/summary.md` with goal, status, step results, and key findings.

---

## Reference Pipelines

Use these as templates. Match your pipeline complexity to the goal.

### Easy (2-3 steps) — "Fix all lint warnings"

| Step | Role | Task Summary | Depends On |
|------|------|-------------|-----------|
| S1 | evaluator | Run `ruff check .` and report all warnings with file locations | - |
| S2 | builder | Fix every warning from S1. Run `ruff check .` to verify clean. | S1 |
| S3 | archivist | Archive: what was fixed, how many warnings resolved | S2 |

**Gate rules:** After S1: PROCEED if warnings found; ABORT if already clean (nothing to do). After S2: PROCEED if `ruff check .` passes.

No parallelism needed — each step depends on the previous.

### Medium (5-6 steps) — "Research and fix the auth bug"

| Step | Role | Task Summary | Depends On |
|------|------|-------------|-----------|
| S1 | researcher | Research the auth bug: read auth middleware, search for similar issues, check error logs | - |
| S2 | evaluator | Run baseline eval to capture current scores | - |
| S3 | strategist | Generate fix hypotheses from S1 research. Pick the most targeted fix. | S1, S2 |
| S4 | builder | Implement the top hypothesis from S3 on a feature branch. Open PR. | S3 |
| S5 | reviewer | Review the PR: check correctness, scope, test coverage | S4 |
| S6 | archivist | Archive: root cause, fix approach, eval comparison | S5 |

**Gate rules:**
- After S1: PROCEED if root cause identified; REDIRECT if research is too shallow
- After S3: PROCEED if hypothesis is specific and scoped to one PR
- After S5: PROCEED if reviewer passes; ABORT if guard violations

S1 and S2 run in parallel (both depend on nothing).

### Hard (7-8 steps) — "Profile API latency, optimize, and validate"

| Step | Role | Task Summary | Depends On |
|------|------|-------------|-----------|
| S1 | researcher | Profile all API endpoints: measure latency, identify the top 3 slowest, research optimization techniques for each | - |
| S2 | evaluator | Run baseline eval, capture current scores and latency metrics | - |
| S3 | strategist | Rank optimizations by expected impact. Produce one hypothesis per slow endpoint, prioritized. | S1, S2 |
| S4 | builder | Implement the #1 optimization from S3 | S3 |
| S5 | reviewer | Review the optimization PR: correctness, no regressions, benchmarks included | S4 |
| S6 | evaluator | Run post-optimization eval. Compare latency and scores to S2 baseline. | S5 |
| S7 | builder | Implement #2 optimization if S6 shows improvement (skip if regression) | S6 |
| S8 | archivist | Archive: performance profile, optimizations applied, before/after metrics | S7 |

**Gate rules:**
- After S1: PROCEED if hot paths identified with measurable latency data
- After S3: PROCEED if hypotheses include expected latency reduction
- After S5: PROCEED if reviewer passes; ABORT if correctness issues
- After S6: PROCEED if latency improved; ABORT if regression (revert S4)
- After S7: same gate as S5-S6 pattern

S1 and S2 run in parallel. S7 is conditional — skip if S6 shows regression.
