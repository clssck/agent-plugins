# Keyboard Shortcuts Reference

---

## Basic Input

| Shortcut | Action |
|----------|--------|
| `Enter` | Submit message |
| `Ctrl+J` | Insert newline (multiline) |
| `Ctrl+V` | Paste from clipboard |
| `Ctrl+C` | Cancel / Exit |
| `Escape` | Cancel streaming |

---

## Text Editing

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` | Kill line (cut to end) |
| `Ctrl+Y` | Yank (paste killed text) |
| `Ctrl+W` | Delete word left |
| `Ctrl+U` | Clear line |

---

## Navigation

| Shortcut | Action |
|----------|--------|
| `Up` / `Down` | Command history |
| `Left` / `Right` | Move cursor |
| `Ctrl+A` / `Home` | Line start |
| `Ctrl+E` / `End` | Line end |
| `Ctrl+Left/Right` | Word jump |

---

## History

| Shortcut | Action |
|----------|--------|
| `Ctrl+R` | Search prompt history |
| `Up Arrow` | Previous command |
| `Down Arrow` | Next command |

---

## View Controls

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Cycle display mode (compact / expanded / transcript) |
| `Ctrl+T` | SQL table view |
| `Ctrl+P` | Toggle plan mode |
| `Ctrl+B` | Background bash process |
| `Ctrl+D` | Open fullscreen todo view |
| `Ctrl+G` | Web search results |

---

## Process Control

| Shortcut | Action |
|----------|--------|
| `Ctrl+C` | Cancel/Interrupt |
| `Escape` | Cancel streaming |

---

## Mode Switching

| Shortcut | Action |
|----------|--------|
| `Shift+Tab` | Cycle modes |

Modes: Confirm Actions ↔ Bypass Safeguards (Plan mode is separate, toggled via `Ctrl+P`)

---

## Special Characters

| Char | Action | Example |
|------|--------|---------|
| `@` | File completion | `@src/app.ts` |
| `@$L-L` | File with lines | `@src/app.ts$10-50` |
| `@{}` | Path with spaces | `@{my file.txt}` |
| `$` | Skill tagging | `$skill-name task` |
| `#` | Snowflake table | `#DB.SCHEMA.TABLE` |
| `!` | Run bash | `!git status` |
| `/` | Slash command | `/help` |
| `?` | Quick help | `?` |

---

## Fullscreen Views

| Shortcut | Action |
|----------|--------|
| `q` / `Escape` | Exit |
| `Up` / `Down` / `j` / `k` | Scroll |
| `Page Up` / `Page Down` | Page scroll |
| `Home` / `End` | Top / Bottom |

---

## Tips

1. `Ctrl+J` for multiline input
2. `Ctrl+R` to search prompt history
3. `Shift+Tab` for quick mode switching
4. `Ctrl+B` to background long bash commands
5. `?` for instant help overlay
