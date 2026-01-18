# Superpowers Integration Design

## Overview

Integrate superpowers methodology skills into work tool workers. Workers get explicit skill references at each workflow step while work's infrastructure (gates, hooks, database) remains unchanged.

## Context

- **Superpowers**: Methodology library (14 skills) - TDD, debugging, brainstorming, planning, reviews
- **Work tool**: Session orchestration - spawns workers in terminal tabs, tracks stages, review gates

These are complementary: work handles WHERE/WHEN, superpowers handles HOW.

## Design Decision

**Approach**: Update worker prompt to explicitly reference superpowers skills at each workflow step.

**Why not deeper integration?**
- Separation of concerns - infrastructure vs methodology
- Less coupling - superpowers can evolve independently
- Work's gate mechanism (marker files, hooks) already works

## Changes

### 1. Update `generate_prompt()` in `work` script

Map superpowers skills to workflow steps:

| Step | Superpowers Skill |
|------|-------------------|
| Understand & Plan | `brainstorming`, `writing-plans` |
| Implement | `test-driven-development`, `systematic-debugging`, `requesting-code-review` |
| Verify | `verification-before-completion` |
| Address feedback | `receiving-code-review` |
| Merge | `finishing-a-development-branch` |

### 2. Add `work --plan <file>` command

Execute plan files directly with smooth workflow from planning to implementation:

```bash
work --plan docs/plans/2026-01-18-my-feature.md
```

**Flow:**
1. Validate plan file exists
2. Extract branch name from plan filename (e.g., `plan/my-feature`)
3. Create worktree from `origin/main`
4. Get plan into worktree:
   - If committed: cherry-pick the plan commit
   - If uncommitted: copy file and commit in worktree
5. Spawn worker with plan-specific prompt referencing `superpowers:executing-plans`

**Why not just embed in prompt?**
- Plan in prompt loses context in long conversations
- Worker can't re-read the plan when needed
- Having a file allows worker to reference specific sections

**Flexibility:**
- Committed plans: cherry-picked (preserves git history)
- Uncommitted plans: copied and committed in worktree (works for hand-written or in-progress plans)

### 3. No changes to

- `work --review` (keep as gate)
- Hooks (stage detection unchanged)
- Database schema
- `.work.toml` structure

## Assumptions

- Superpowers is installed globally via Claude Code plugin
- Workers inherit global plugin configuration
- If superpowers not installed, skill references are ignored (acceptable)

## Future Considerations (not in scope)

- `.work.toml` overrides for skill selection per project
- Skill availability detection
- Tighter review integration (replacing work's review with superpowers subagent)
