# Target workspace resolution

`cortex ws` resolves the target itself for file ops — this reference is for SQL flows (lifecycle, RBAC, replication, recovery) that need a verified FQN, or partial-name lookups when `cortex ws` errors with "does not exist or not authorized".

## Partial-name lookup

Use `SHOW TERSE WORKSPACES` (smaller payload than `SHOW WORKSPACES`) with the narrowest scope you have, plus a `LIKE` filter when you have any partial-name signal:

| Form | When |
|---|---|
| `SHOW TERSE WORKSPACES IN SCHEMA <db>.<schema> LIKE '<pattern>'` | Schema + name pattern known |
| `SHOW TERSE WORKSPACES IN DATABASE <db> LIKE '<pattern>'` | Database + name pattern |
| `SHOW TERSE WORKSPACES LIKE '<pattern>'` | Account-wide, name-narrowed |
| `SHOW TERSE WORKSPACES [IN SCHEMA … | IN DATABASE …]` | No name signal; scope as tightly as possible |

`SHOW TERSE WORKSPACES` (no scope, no filter) is the last resort.

## Anti-substitution

If the user named a specific target and it isn't found, **report and STOP** — don't silently substitute a similar-looking workspace. Useful shape:

> "I couldn't find a workspace matching `<input>`. Did you mean one of: `<close matches from SHOW TERSE>`?"

Silent substitution can corrupt data the user didn't intend to touch.

## Collisions

If a partial name matches multiple workspaces, show the candidates and ask the user to disambiguate.

## "My workspace" defaults to DEFAULT$

When the user says "my workspace" (singular, with no further qualifier), target `USER$.PUBLIC.DEFAULT$` (the Snowsight "My Workspace" alias).

**Do not infer a non-default personal workspace from contextual cues.** Filename matches with workspace names, recently-created workspaces, and workspace-name similarity to staging directories are NOT signals to retarget — they are coincidence. The user said "my workspace"; treat that as DEFAULT$ unless they explicitly name a different one.

If you genuinely need to ask, ask explicitly. If you cannot ask (headless / non-interactive), default to `USER$.PUBLIC.DEFAULT$` and explicitly report which workspace you targeted in your response so the user can correct course on the next turn.

## Quoting

For SQL callers, identifier rules apply: unquoted = case-insensitive (uppercased before match); quoted = literal.

`cortex ws` accepts both forms in the FQN segment of its `DB.SCH.WS:/path` grammar — quoted identifiers preserve case and special characters (e.g., `MY_DB.PUBLIC."weird:ws":/path`). Pass the raw FQN as the user gave it.
