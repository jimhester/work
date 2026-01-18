# Visibility and Notifications Design

## Problem Statement

When running multiple workers:
1. **Terminal sessions lose context** - Claude Code overwrites tab titles, can't match terminal to issue/PR
2. **Missing attention signals** - Workers get blocked on permissions or finish, but no notification
3. **No quick view** - Have to manually check each worker to see what needs attention

## Features

### Feature 1: Custom Status Line

**File:** `~/.claude/scripts/work-statusline.sh`

**Display format:**
```
#42 → PR #187 | implementing | ████░░░░ 52%
```

- `#{issue}` - Original issue number
- `→ PR #{pr}` - PR number if registered (omit if none)
- `{stage}` - Current worker stage
- `{context_bar} {percent}%` - Context usage with color-coded progress bar

**Color coding for context usage:**
- Green: <50%
- Yellow: 50-75%
- Orange: 75-90%
- Red: >90%

**Fallback:** When not in a worker session (no `WORK_WORKER_ID` env var), show standard info (branch, git status).

**Implementation:**
1. Script reads `WORK_WORKER_ID` environment variable
2. Queries `~/.worktrees/work-sessions.db` for issue, PR number, stage
3. Parses Claude session files for context usage (similar to claude-code-tools approach)
4. Outputs formatted status line

**Installation:**
`work --init` will:
1. Copy `work-statusline.sh` to `~/.claude/scripts/`
2. Add to `~/.claude/settings.json`:
   ```json
   {
     "statusLineCommand": "~/.claude/scripts/work-statusline.sh"
   }
   ```

### Feature 2: Desktop Notifications

**Augment existing hook:** `hooks/work-stage-detector.sh`

**Triggers:**
- Stage → `done`: Worker completed successfully
- Stage → `blocked` or `merge_conflicts`: Worker hit a problem
- Permission prompt detected: Worker waiting for user approval

**Notification function:**
```bash
toast() {
  local title="$1" body="$2"
  if [[ "$(uname -r)" == *microsoft* ]]; then
    # WSL2 - Windows toast via PowerShell (no dependencies)
    powershell.exe -Command "
      Add-Type -AssemblyName System.Windows.Forms
      \$n = New-Object System.Windows.Forms.NotifyIcon
      \$n.Icon = [System.Drawing.SystemIcons]::Information
      \$n.Visible = \$true
      \$n.ShowBalloonTip(5000, '$title', '$body', 'Info')
    " &>/dev/null &
  elif [[ "$OSTYPE" == darwin* ]]; then
    osascript -e "display notification \"$body\" with title \"$title\""
  elif command -v notify-send &>/dev/null; then
    notify-send "$title" "$body"
  fi
}
```

**Configuration in `.work.toml`:**
```toml
[notifications]
enabled = true
on_done = true
on_blocked = true
on_permission_prompt = true
```

**Notification content:**
- Done: `"Worker #42 complete"` / `"auth-fix is ready for review"`
- Blocked: `"Worker #42 blocked"` / `"Merge conflict in auth-fix"`
- Permission: `"Worker #42 waiting"` / `"Permission prompt - needs approval"`

### Feature 3: Enhanced `--status`

**New output format:**
```
$ work --status
⏳ #42  auth-fix       PR #187  waiting (permission)   5m idle
✗  #61  docs-update    —        merge_conflicts        12m idle
●  #58  api-refactor   PR #201  implementing           active
✓  #67  test-cleanup   PR #205  done                   2m ago

4 workers: 1 active, 2 need attention, 1 done
```

**Status icons:**
- `⏳` - Waiting for input (permission prompt)
- `✗` - Failed/blocked/merge_conflicts
- `●` - Active (in progress)
- `✓` - Done

**Sort order:** Workers needing attention first, then active, then done.

**Columns:**
1. Status icon
2. Issue number
3. Branch name (truncated if needed)
4. PR number or `—`
5. Stage
6. Activity (`active`, `Xm idle`, `Xm ago`)

**Summary line:** Quick count of worker states.

**Schema changes:**
Add `last_activity_at` timestamp to workers table, updated by hooks on each tool use.

## Not Included (Deferred)

**File visibility for coordination** - Considered showing which files other workers are touching to reduce merge conflicts. Deferred because:
- Prompting on spawn adds friction
- Workers handle their own merge conflicts
- Unclear if upfront visibility actually helps

May revisit with auto-rebase prompts or post-conflict guidance if conflicts become a bigger pain point.

## Implementation Order

1. **Enhanced `--status`** - Low complexity, immediate value
2. **Desktop notifications** - Augments existing hook, low complexity
3. **Custom status line** - Medium complexity, requires Claude session file parsing
