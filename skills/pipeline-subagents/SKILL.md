---
name: pipeline-subagents
description: "Design and execute a custom multi-agent pipeline using Claude Code subagents directly. Spawns researcher, builder, etc. via the Agent tool with native parallel and background execution. Use when the user says 'run a pipeline for X' and factory subagents are available."
disable-model-invocation: true
argument-hint: "<goal>"
---

# Pipeline (Subagents) — Dynamic Multi-Agent Orchestrator

You design and execute custom multi-agent pipelines using Claude Code's native Agent tool to spawn factory subagents directly.

The user wants: **$ARGUMENTS**

## Setup

```bash
mkdir -p .factory/pipeline
```

## Your Agents

Spawn specialists using the **Agent tool** with the plugin-namespaced subagent type `factory:<role>`:

```
Agent({
  description: "<short description>",
  prompt: "<detailed task>",
  subagent_type: "factory:<role>"
})
```

| Subagent Type | Purpose |
|---------------|---------|
| factory:researcher | Web research, codebase analysis, domain studies |
| factory:strategist | Generate prioritized hypotheses from observations |
| factory:builder | Implement code changes on a feature branch, open PRs |
| factory:reviewer | Review PRs, guard checks, keep/revert verdicts |
| factory:evaluator | Run evals, compare before/after scores |
| factory:archivist | Record findings to `.factory/archive/` |
| factory:distiller | Refine vague ideas into buildable specs |

Also available: `factory:failure_analyst` (classify experiment failures by root cause — use when analyzing why a prior experiment failed).

### Parallel Execution

Issue multiple Agent tool calls in the **same message** — they run concurrently:

```
Agent({ subagent_type: "factory:researcher", prompt: "Research the auth bug..." })
Agent({ subagent_type: "factory:evaluator", prompt: "Run baseline eval..." })
```

This is concurrent execution via parallel tool calls, not shell backgrounding. Each Agent call is still individually synchronous.

### Background Execution

For non-blocking steps (e.g., archival):

```
Agent({ subagent_type: "factory:archivist", prompt: "Archive findings...", run_in_background: true })
```

## Phase 1: Design the Pipeline

1. **Understand the goal** — what outcome is desired? Which agents are needed?
2. **Inspect project state** (use Bash tool):
   ```bash
   ls .factory/config.json 2>/dev/null && cat .factory/config.json
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
- **Maximize parallelism** — steps whose dependencies are all satisfied and that don't depend on each other can be spawned in the same message
- **Mandatory archival** — always include at least one archivist step at the end
- **Gate rules** — define PROCEED/REDIRECT/ABORT criteria for critical transitions

## Phase 2: Execute the Pipeline

Process steps in topological order:

1. **Identify next batch** — steps whose dependencies are all complete
2. **Build prompts** — incorporate output from prior steps (agent results are returned directly)
3. **Emit start event** and **invoke agents:**
   ```bash
   factory emit agent.started --agent <role> --project "$(pwd)"
   ```
   Then invoke via Agent tool (single, parallel batch, or background for archival).
4. **Read results** — Agent tool returns subagent output directly
5. **Persist review and emit completion:**
   ```bash
   mkdir -p .factory/reviews
   factory emit agent.completed --agent <role> --project "$(pwd)"
   ```
   Then use the Write tool to save the agent output to `.factory/reviews/<role>-latest.md`
6. **Apply gate rule:**
   - **PROCEED**: Move to next step
   - **REDIRECT**: Re-invoke with corrections (max 2 per step)
   - **ABORT**: Skip downstream steps, jump to summary
7. **Repeat** until done

### Error Recovery

- Agent error: retry once with simpler prompt
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

**Gate rules:** After S1: PROCEED if warnings found; ABORT if already clean. After S2: PROCEED if `ruff check .` passes.

**Execution:** Sequential — each step depends on the previous. S3 can run in background.

```
Agent({ subagent_type: "factory:evaluator", prompt: "Run ruff check . ..." })
# read result, then:
Agent({ subagent_type: "factory:builder", prompt: "Fix these warnings: {S1 result} ..." })
# read result, then:
Agent({ subagent_type: "factory:archivist", prompt: "Archive lint fixes ...", run_in_background: true })
```

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

**Execution:** S1 and S2 in parallel (same message), then sequential:

```
# Parallel: S1 + S2
Agent({ subagent_type: "factory:researcher", prompt: "Research auth bug ..." })
Agent({ subagent_type: "factory:evaluator", prompt: "Run baseline eval ..." })
# Wait for both, then S3:
Agent({ subagent_type: "factory:strategist", prompt: "Given research: {S1} and baseline: {S2}, generate fix hypotheses ..." })
# ... sequential from here
```

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

**Execution:** S1 and S2 in parallel. S7 is conditional — skip if S6 shows regression.
