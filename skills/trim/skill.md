---
name: trim
description: Trim large tool outputs to free context space
---

# Trim Session Context

Trimming creates a new session file with large tool outputs truncated, typically saving 30-50% context.

**IMPORTANT:** Trimming requires exiting and resuming. The current session cannot be trimmed in-place.

## Steps

1. **Run the trim command:**
   ```bash
   work --trim
   ```

2. **Tell the user to exit and resume.** After the command runs, you MUST clearly instruct:
   > I've created a trimmed version of this session. To continue with reduced context:
   > 1. Exit this session (press `Ctrl+C` or type `/exit`)
   > 2. Run: `claude --resume <session-id>` (using the ID shown above)
   >
   > The trimmed session preserves our conversation but truncates large tool outputs.
   > If you need full content of something that was truncated, I can re-run the tool or search episodic-memory.

## When to Use

- Context is 60-80% full and you want to continue the current task
- You have large tool outputs (file reads, grep results) that are no longer needed in full

## When to Use /rollover Instead

- Context is >85% full (trim may not free enough space)
- You're starting a new phase of work and want a clean handoff
- Trim savings would be <10%

## Configuration

In `.work.toml`:
```toml
[context]
trim_threshold_chars = 500           # Characters to keep before truncating
trim_target_tools = ["Read", "Bash", "Grep", "Glob"]  # Tools to trim
```
