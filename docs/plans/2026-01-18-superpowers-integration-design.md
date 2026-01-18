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

### 2. No changes to

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
