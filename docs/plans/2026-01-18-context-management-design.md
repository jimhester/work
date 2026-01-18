# Context Management Design

## Problem Statement

Worker context quality degrades around 60% usage, well before Claude's auto-compaction triggers at 95%. Auto-compaction is lossy and doesn't preserve important decisions or context effectively. Workers need proactive tools to manage context before degradation occurs.

## Goals

1. Detect high context usage and alert workers
2. Provide `/trim` to free space while staying in session
3. Provide `/rollover` for clean handoff to fresh session
4. Preserve full context in episodic-memory for retrieval
5. Track session lineage for debugging and analysis

## Non-Goals

- Replacing Claude's auto-compaction (it remains as last resort)
- Automatic trimming/rollover without worker control
- Complex sub-agent analysis (leverage episodic-memory instead)

## Design

### Overview

```
Context Usage:
0%────────60%────────75%────────85%────────95%────────100%
           │          │          │          │
           │          │          │          └─ Auto-compaction (lossy, avoid)
           │          │          └─ Urgent: /trim or /rollover now
           │          └─ Recommend: /trim or /rollover soon
           └─ Gentle reminder: Consider /trim if quality degraded

Actions:
1. /trim    - Remove old tool outputs, stay in session (can free 30-50%)
2. /rollover - Fresh session with handoff summary + episodic-memory retrieval
```

### Component 1: Hook-Based Context Warnings

**File:** `hooks/work-stage-detector.sh` (addition to existing hook)

The PostToolUse hook monitors context usage and injects system reminders:

- **60%**: `"Context at 62%. Consider /trim if responses feel degraded."`
- **75%**: `"Context at 76%. Recommend /trim now or /rollover soon."`
- **85%**: `"Context at 87%. Use /trim or /rollover before auto-compaction at 95%."`

Reminders are rate-limited (every 60 seconds) to avoid noise.

**Implementation:**

```bash
inject_context_reminder() {
    local pct="$1"

    if [[ $pct -ge 85 ]]; then
        echo "<system-reminder>Context at ${pct}%. Use /trim or /rollover now to avoid lossy auto-compaction at 95%.</system-reminder>"
    elif [[ $pct -ge 75 ]]; then
        echo "<system-reminder>Context at ${pct}%. Recommend /trim soon, or /rollover if trim isn't helping.</system-reminder>"
    elif [[ $pct -ge 60 ]]; then
        echo "<system-reminder>Context at ${pct}%. Consider /trim if response quality feels degraded.</system-reminder>"
    fi
}
```

### Component 2: `/trim` Skill

**Purpose:** Conservatively remove old tool outputs to free context space while staying in the same session.

**Mechanism:** Adapts the approach from [claude-code-tools](https://github.com/pchalasani/claude-code-tools):
1. Parse session JSONL file
2. Identify tool results exceeding threshold (default 500 chars)
3. Truncate to first N chars + reference to parent file
4. Create new session file with trim metadata
5. Resume with `claude --resume {new-session-id}`

**Files:**
- `skills/trim/skill.md` - Skill definition
- `work --trim` - CLI command that does the work

**Skill content:**

```markdown
---
name: trim
description: Trim large tool outputs to free context space
---

To free context space, run:

\`\`\`bash
./work --trim
\`\`\`

This will:
1. Sync current session to episodic-memory (preserve full content)
2. Find tool outputs over 500 characters
3. Truncate them, keeping first 500 chars + reference to original
4. Resume session with trimmed content

Typical savings: 30-50% on first trim.

If trimming doesn't free meaningful space, use /rollover instead.
```

**Python implementation:**

```python
def trim_session(
    session_file: Path,
    threshold: int = 500,
    target_tools: set = {"Read", "Bash", "Grep", "Glob"},
) -> dict:
    """
    Trim large tool outputs from a Claude session file.
    Adapted from claude-code-tools trim_session_claude.py.
    """
    # 1. Sync to episodic-memory first
    subprocess.run(["episodic-memory", "sync"], check=False)

    # 2. Build tool_use_id -> tool_name mapping (first pass)
    tool_map = build_tool_name_mapping(session_file)

    # 3. Process and truncate (second pass)
    output_file = session_file.with_suffix('.trimmed.jsonl')
    stats = process_and_truncate(
        input_file=session_file,
        output_file=output_file,
        tool_map=tool_map,
        target_tools=target_tools,
        threshold=threshold,
    )

    # 4. Inject trim metadata
    inject_trim_metadata(output_file, parent_file=session_file, stats=stats)

    # 5. Assign new session ID and resume
    new_session_id = generate_session_id()
    update_session_id(output_file, new_session_id)

    return {
        "trimmed_count": stats["trimmed_count"],
        "tokens_saved": stats["tokens_saved"],
        "new_session_id": new_session_id,
    }
```

### Component 3: `/rollover` Skill

**Purpose:** Start fresh session when trimming isn't enough, with handoff summary and episodic-memory for retrieval.

**Mechanism:**
1. Worker generates brief handoff summary (~500 words)
2. Sync current session to episodic-memory (full content preserved)
3. Record session end in database with lineage
4. Start new Claude session with summary injected
5. New session retrieves details via episodic-memory as needed

**Files:**
- `skills/rollover/skill.md` - Skill definition
- `work --rollover --summary-file <file>` - CLI command

**Skill content:**

```markdown
---
name: rollover
description: Start fresh session when context is high, preserving continuity
---

## Step 1: Generate Handoff Summary

Write a BRIEF summary (~500 words max):

\`\`\`
### Current Task
[Issue/goal and status in 1-2 sentences]

### Key Decisions
- [Decision]: [rationale] (max 5, 1 line each)

### Modified Files
- [file]: [what changed] (1 line each)

### Immediate Next Steps
1. [Next action]
2. [Following action]

### Critical Context
[Blockers, gotchas, important findings]
\`\`\`

## Step 2: Execute Rollover

\`\`\`bash
cat > /tmp/rollover-summary.txt << 'EOF'
[your summary]
EOF

./work --rollover --summary-file /tmp/rollover-summary.txt
\`\`\`

## Step 3: In New Session

Summary is injected automatically. For details not in summary:

\`\`\`
mcp__episodic-memory__search with query: "what you need"
\`\`\`
```

**Continuation prompt (injected into new session):**

```markdown
## Session Continuation

This is session #{n} for {issue_ref}.
Previous session rolled over at {pct}% context to preserve quality.

### Handoff Summary

{summary}

### Retrieving Details

The full previous session is indexed in episodic-memory. For details not in
the summary above, search with:

```
mcp__episodic-memory__search with query: "what you need to find"
```

Example queries:
- "decision about [topic]"
- "error in [component]"
- "changes to [filename]"

### Lineage

Parent session: {parent_session_file}
Worker ID: {worker_id}

---

Continue from the handoff summary. Your next step is in "Immediate Next Steps" above.
```

### Component 4: Database Schema Addition

**New table for session tracking:**

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    worker_id INTEGER REFERENCES workers(id),
    session_number INTEGER,       -- 1, 2, 3...
    session_id TEXT,              -- Claude session UUID
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    end_reason TEXT,              -- 'rollover', 'trim', 'completed'
    context_at_end INTEGER,       -- Percentage when ended
    summary TEXT                  -- Handoff summary (for rollover)
);

CREATE INDEX IF NOT EXISTS idx_sessions_worker ON sessions(worker_id);
```

**Metadata injection (for lineage tracing):**

New sessions get `continue_metadata` in first JSON line:

```json
{
  "continue_metadata": {
    "parent_session_file": "/path/to/parent.jsonl",
    "continued_at": "2026-01-18T12:00:00Z",
    "worker_id": 42,
    "reason": "rollover"
  }
}
```

Trimmed sessions get `trim_metadata`:

```json
{
  "trim_metadata": {
    "parent_file": "/path/to/parent.jsonl",
    "trimmed_at": "2026-01-18T12:00:00Z",
    "threshold": 500,
    "trimmed_count": 23,
    "tokens_saved": 45000
  }
}
```

### Component 5: Worker Prompt Addition

**Added to spawn prompt:**

```markdown
## Context Management

Your context window has limited capacity. Quality degrades around 60% usage,
and auto-compaction (lossy) triggers at 95%.

### Monitoring
- Status line shows current context percentage
- You'll receive system reminders at 60%, 75%, and 85%

### Actions

**At 60%+** - Consider `/trim` if you notice degraded responses:
```
/trim
```
This removes large old tool outputs while preserving decisions and recent work.
Can free 30-50% of context. Use multiple times if needed.

**At 75%+ or trim ineffective** - Use `/rollover`:
```
/rollover
```
This starts a fresh session with your handoff summary. Full context is
preserved in episodic-memory for retrieval.

### Priority Order
1. `/trim` - Least disruptive, stay in session
2. `/rollover` - Clean handoff, fresh context
3. Auto-compaction - Last resort (lossy, avoid if possible)
```

### Component 6: Configuration

**`.work.toml` additions:**

```toml
[context]
# Thresholds for system reminders (percentages)
warn_threshold = 60
recommend_threshold = 75
urgent_threshold = 85

# Trim settings
trim_threshold_chars = 500
trim_target_tools = ["Read", "Bash", "Grep", "Glob"]

# Reminder frequency
check_interval_seconds = 60
```

## Interaction with episodic-memory

**Key insight:** episodic-memory syncs and indexes session files separately from our modifications.

**Flow:**
1. Before trim/rollover, sync current session to episodic-memory
2. Full content is preserved in `~/.config/superpowers/conversation-archive/`
3. Trimmed/new sessions maintain lineage pointers to parent
4. Workers can retrieve any detail via semantic search

**No conflicts because:**
- Trim creates new file (original preserved)
- Rollover creates new session (original preserved)
- episodic-memory indexes originals before modification

## Implementation Order

1. **Database schema** - Add sessions table
2. **`/trim` skill + `work --trim`** - Port from claude-code-tools
3. **`/rollover` skill + `work --rollover`** - Implement handoff flow
4. **Hook reminders** - Add to work-stage-detector.sh
5. **Worker prompt** - Add context management section
6. **Configuration** - Add [context] section support

## Testing

1. **Trim:** Verify tool outputs are truncated, lineage preserved, resume works
2. **Rollover:** Verify summary injection, episodic-memory retrieval, session tracking
3. **Hooks:** Verify reminders appear at correct thresholds, rate-limited
4. **Integration:** Full workflow - work until 60%, trim, work until 75%, rollover, retrieve

## References

- [claude-code-tools](https://github.com/pchalasani/claude-code-tools) - Trim and rollover implementation
- [episodic-memory](https://github.com/obra/episodic-memory) - Session archiving and search
- [Claude Code issue #6549](https://github.com/anthropics/claude-code/issues/6549) - Better compaction proposal
- [Claude Code issue #18417](https://github.com/anthropics/claude-code/issues/18417) - Native session persistence request
