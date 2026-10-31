#!/bin/bash
# SessionStart hook: prints the session memory file so every new session starts with it.
f="${CLAUDE_PROJECT_DIR:-$(pwd)}/docs/algos/SESSION_MEMORY.md"
[ -f "$f" ] && { echo "Session memory (docs/algos/SESSION_MEMORY.md):"; cat "$f"; }
exit 0
