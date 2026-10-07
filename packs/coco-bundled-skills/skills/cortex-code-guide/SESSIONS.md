# Session Management Reference

Cortex Code maintains conversation sessions that can be resumed, forked, rewound, and compacted.

---

## Resume Sessions

### CLI

```bash
cortex -r last                      # Resume last session
cortex -r <session_id>              # Resume specific session
cortex resume                       # Interactive session picker
```

### Slash Command

```
/resume                             # Open fullscreen session selector
```

Lists up to 100 previous sessions. Select one to continue where you left off.

---

## Fork Conversations

```
/fork                               # Fork from selected message
/fork my-experiment                  # Fork with custom name
```

Creates a new session branched from a specific point in the current conversation. Opens an interactive message selector to choose the fork point.

Use cases:

- Try an alternative approach without losing current progress
- Branch off to explore a tangent
- Create a checkpoint before risky changes

---

## Rewind

```
/rewind                             # Interactive selector
/rewind 3                           # Rewind 3 user messages
```

Rolls back the conversation to a previous state. The rewound messages are discarded.

---

## Compact / Summarize

```
/compact                            # Summarize and clear history
/compact focus on the API changes   # Summarize with custom instructions
```

Clears conversation history but retains a summary in context. Useful when:

- Context window is getting full
- You want to refocus the conversation
- Switching to a different subtask within the same session

The optional instructions guide what the summary should emphasize.

---

## Diff Viewer

```
/diff                               # Fullscreen git diff viewer
/diff --staged                      # Show only staged changes
```

Shows uncommitted changes in a fullscreen scrollable view with file stats, hunks, and line numbers. Aliases: `/changes`, `/review`.

---

## Session Naming

```
/rename my-feature-work             # Rename current session
```

Named sessions are easier to find when resuming later.

---

## Tips

1. Use `/compact` liberally when context gets long -- it preserves key information while freeing space
2. `/fork` before trying experimental approaches so you can return to the original path
3. `/rewind` is useful when the agent went down a wrong path
4. Name important sessions with `/rename` so they are easy to find later
