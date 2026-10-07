---
name: business-ontology-approval-patterns
description: "Filtered-approve protocol for Business Ontology relationships and associations. Load when running batch approvals in import or create flows to avoid blindly approving the account-wide draft queue."
---

# Approval Patterns

## Why filtered approve matters

`APPROVE_ALL_GLOSSARY_RELATIONSHIPS()` and `APPROVE_ALL_GLOSSARY_ASSETS()` approve every item
in the **account-wide** draft queue — not just items from the current session. Calling them
blindly can approve probe data, test entries, or another team's unreviewed drafts.

## Session draft tracking

**Relationships:** After each `DRAFT_GLOSSARY_RELATIONSHIP` call, record the `(sourceTermId, targetTermId, type)` tuple from the response. The response does **not** include a `suggestionId` — use the tuple as the session identity key.

```json
// session_relationship_drafts (keep in context for the session)
[{"source": "<sourceTermId>", "target": "<targetTermId>", "type": "DERIVES"}, ...]
```

**Associations:** After each `DRAFT_GLOSSARY_ASSET` call, record `(termId, refType, fqn)`:

```json
// session_association_drafts
[{"termId": "<termId>", "refType": "TABLE", "fqn": "DB.SCHEMA.TABLE"}, ...]
```

## Filtered-approve: relationships

### Step 1 — Inspect the draft queue (best-effort)

> ⚠️ `GET_GLOSSARY_RELATIONSHIP_DRAFTS` requires non-standard account enablement. If it fails
> with a gate error, skip to Step 3.

```sql
CALL SYSTEM$GET_GLOSSARY_RELATIONSHIP_DRAFTS();
```

### Step 2 — Compare and prompt if foreign items exist

Match returned drafts against `session_relationship_drafts` by `(source, target, type)` tuple.
If `queue_total - session_count > 0`:

```
I drafted N relationships this session. The queue also has M items from other sessions.
  approve only mine  → individual APPROVE calls for session items only
  approve all        → APPROVE_ALL (includes other sessions' items)
```

- **"Approve only mine"** → for each tuple in `session_relationship_drafts` (use termIds — domain name is not returned by DRAFT_GLOSSARY_RELATIONSHIP and cannot be reconstructed from the tuple):
  ```sql
  CALL SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP('<sourceTermId>', '<targetTermId>', '<type>');
  ```
- **"Approve all"** (explicit user choice):
  ```sql
  CALL SYSTEM$APPROVE_ALL_GLOSSARY_RELATIONSHIPS();
  ```

### Step 3 — Gate unavailable or queue has only session items

Use individual calls per `session_relationship_drafts` — safe regardless of gate status.

> `APPROVE_GLOSSARY_RELATIONSHIP` accepts **either** FQN (`'<domain>.<term>'`) **or** a bare `termId` string — use whichever form you have from the DRAFT response tuple. When only IDs are available, pass the IDs directly:

```sql
-- Using termIds from the session_relationship_drafts tuple (preferred when FQN is not in scope)
CALL SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP('<sourceTermId>', '<targetTermId>', '<type>');

-- Using FQN (when domain context is known)
CALL SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP('<domain>.<sourceTerm>', '<domain>.<targetTerm>', '<type>');
```

## Filtered-approve: associations

### Step 1 — Inspect the draft queue (best-effort)

> ⚠️ `GET_GLOSSARY_ASSOCIATION_DRAFTS` requires non-standard account enablement. If it fails
> with a gate error, skip to Step 3.

```sql
CALL SYSTEM$GET_GLOSSARY_ASSOCIATION_DRAFTS();
```

### Step 2 — Compare and prompt if foreign items exist

Match returned drafts against `session_association_drafts` by `(termId, refType, fqn)` tuple.
If `queue_total - session_count > 0`:

```
I drafted N associations this session. The queue also has M items from other sessions.
  approve only mine  → individual APPROVE calls for session items only
  approve all        → APPROVE_ALL (includes other sessions' items)
```

- **"Approve only mine"** → for each tuple in `session_association_drafts` (use termId — domain name is not stored in the tracking tuple):
  ```sql
  CALL SYSTEM$APPROVE_GLOSSARY_ASSET('<termId>', '{"refType": "<refType>", "fqn": "<fqn>"}');
  ```
- **"Approve all"** (explicit user choice):
  ```sql
  CALL SYSTEM$APPROVE_ALL_GLOSSARY_ASSETS();
  ```

### Step 3 — Gate unavailable or queue has only session items

Use individual calls per `session_association_drafts` — safe regardless of gate status.

> `APPROVE_GLOSSARY_ASSET` accepts **either** a `termId` string **or** FQN (`'<domain>.<term>'`) as the first argument. When only IDs are available from the session tracking tuple, pass the `termId` directly:

```sql
-- Using termId from the session_association_drafts tuple (preferred when FQN is not in scope)
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('<termId>', '{"refType": "<refType>", "fqn": "<fqn>"}');

-- Using FQN (when domain context is known)
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('<domain>.<termName>', '{"refType": "<refType>", "fqn": "<fqn>"}');
```
