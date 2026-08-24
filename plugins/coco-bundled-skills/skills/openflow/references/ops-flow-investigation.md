---
name: openflow-ops-flow-investigation
description: Problem-oriented investigation workflows for diagnosing flow issues. Routes to appropriate tools based on symptoms. Use when flows aren't behaving as expected.
---

# Flow Investigation

Problem-oriented diagnostic workflows for investigating flow issues. This reference helps you choose the right tools based on what you're observing.

**Methodology:** For complex investigations, consider using an investigation diary. See `references/core-investigation-diary.md`.

## Investigation Approach

### First Questions

Before diving into tools, establish context from the user:

1. **What is the expected behavior?** What should the flow be doing?
2. **What is the actual behavior?** What is it doing instead?
3. **When did it start?** Was it ever working? What changed?
4. **What's the scope?** All data, some data, specific patterns?

### Hypothesis-Driven Investigation

1. Form a hypothesis based on symptoms, validate it with the user
2. Choose the tool that can confirm or refute it
3. Observe results
4. Refine hypothesis or move to next
5. Repeat until root cause found

---

## Symptom Router

Match your observation to a diagnostic path:

| Symptom | Likely Cause | Start Here |
|---------|--------------|------------|
| Data not arriving at destination | Many possibilities | [Data Not Arriving](#data-not-arriving) |
| Wrong data format in destination | Transformation or schema issue | [Wrong Data Format](#wrong-data-format) |
| Flow appears stuck | Backpressure, stuck thread, or waiting | [Flow Stuck](#flow-stuck) |
| Intermittent failures | Transient errors, resource issues | [Intermittent Failures](#intermittent-failures) |
| Errors in bulletins | Processor configuration or connectivity | [Bulletin Errors](#bulletin-errors) |
| Slow throughput | Bottleneck or resource constraint | [Slow Throughput](#slow-throughput) |

---

## Data Not Arriving

Data enters the flow but doesn't reach the destination.

### Diagnostic Steps

```
1. Check status
   └── bulletin_errors > 0? → See "Bulletin Errors" section
   └── queued_flowfiles high? → Data stuck in queue, continue below
   └── running_processors = 0? → Flow not started

2. Trace data through the flow
   └── Find where data stops
   └── Inspect FlowFiles before the problem point

3. Check destination processor
   └── Is it running?
   └── Any bulletins?
   └── Check configuration
```

### Tools

```bash
# Step 1: Get status
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

```python
# Step 2: Trace data - find connections with queued FlowFiles
import nipyapi
nipyapi.profiles.switch('<profile>')

pg_id = "<pg-id>"
connections = nipyapi.canvas.list_all_connections(pg_id)

for conn in connections:
    queued = conn.status.aggregate_snapshot.flow_files_queued
    if queued > 0:
        source = conn.component.source.name
        dest = conn.component.destination.name
        print(f"{queued} queued: {source} -> {dest}")
```

```python
# Step 3: Inspect FlowFiles at the stuck point
stuck_conn = "<connection-id>"
flowfiles = nipyapi.canvas.peek_flowfiles(stuck_conn, limit=1)
if flowfiles:
    ff = flowfiles[0]
    print(f"Attributes: {ff.attributes}")
    content = nipyapi.canvas.get_flowfile_content(stuck_conn, ff.uuid)
    print(f"Content preview: {content[:500]}")
```

### Common Causes

| Finding | Likely Cause | Fix |
|---------|--------------|-----|
| Data queued before destination processor | Processor stopped or invalid | Check processor state, enable |
| Bulletin errors on destination | Configuration or connectivity | Fix config, see bulletins |
| Data queued but processor running | Backpressure from destination | Check destination system capacity |
| No data in any queue | Source not producing | Check source processor/connection |
| No data in any queue (CDC) | Waiting on dependency (e.g., snapshot waiting for incremental) | Check wait/notify state, verify dependent flow is connected |

---

## Wrong Data Format

Data arrives but in wrong format (wrong types, missing fields, incorrect values).

### Diagnostic Steps

```
1. Identify the transformation point
   └── Where should format change happen?

2. Inspect FlowFile BEFORE transformation
   └── Is input data correct?

3. Inspect FlowFile AFTER transformation
   └── What's different from expected?

4. Check transformation configuration
   └── RecordPath expressions
   └── Schema settings
   └── Expression Language usage
```

### Tools

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

# Find transformation processor
proc = nipyapi.canvas.get_processor("UpdateRecord")  # or similar

# Get connections
connections = nipyapi.canvas.list_all_connections(pg_id)
in_conn = next(c for c in connections if c.destination_id == proc.id)
out_conn = next(c for c in connections if c.source_id == proc.id)

# Stop processor if running
nipyapi.canvas.schedule_processor(proc, "STOPPED")

# Inspect input
in_ff = nipyapi.canvas.peek_flowfiles(in_conn, limit=1)
if in_ff:
    print("=== INPUT ===")
    print(f"Attributes: {in_ff[0].attributes}")
    in_content = nipyapi.canvas.get_flowfile_content(in_conn, in_ff[0].uuid)
    print(f"Content: {in_content}")

# Run once
nipyapi.canvas.schedule_processor(proc, "RUN_ONCE")

# Inspect output
out_ff = nipyapi.canvas.peek_flowfiles(out_conn, limit=1)
if out_ff:
    print("=== OUTPUT ===")
    print(f"Attributes: {out_ff[0].attributes}")
    out_content = nipyapi.canvas.get_flowfile_content(out_conn, out_ff[0].uuid)
    print(f"Content: {out_content}")
```

### Common Causes

| Finding | Likely Cause | Fix |
|---------|--------------|-----|
| Input already wrong | Upstream issue | Trace further back |
| Output missing fields | RecordPath not matching | Check field paths, case sensitivity |
| Wrong types in output | Schema or type conversion | See `author-snowflake-destination.md` |
| avro.schema missing logicalType | Schema inference issue | See timestamp solution pattern |

---

## Flow Stuck

Flow is running but nothing is moving.

### Diagnostic Steps

```
1. Check status
   └── active_threads > 0? → Threads doing something
   └── queued_flowfiles changing? → Data moving

2. If threads active but no movement
   └── Thread stuck in processor
   └── Check which processor

3. If no active threads
   └── All processors stopped?
   └── Backpressure engaged?
```

### Tools

```bash
# Check overall status
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"

# Check individual processor states
nipyapi --profile <profile> canvas list_all_processors "<pg-id>" | jq '.[] | {name: .component.name, state: .component.state, threads: .status.aggregateSnapshot.activeThreadCount}'
```

```python
# Find processor with active threads
import nipyapi
nipyapi.profiles.switch('<profile>')

processors = nipyapi.canvas.list_all_processors(pg_id)
for proc in processors:
    threads = proc.status.aggregate_snapshot.active_thread_count
    if threads > 0:
        print(f"{proc.component.name}: {threads} active threads")
```

### Common Causes

| Finding | Likely Cause | Fix |
|---------|--------------|-----|
| Threads stuck in one processor | External call hanging | Check network, timeout config |
| Backpressure on all connections | Downstream bottleneck | Increase capacity or fix destination |
| Source processor stopped | Scheduling issue | Check processor state |
| Penalized FlowFiles | Previous failures | Wait or clear penalty |

---

## Intermittent Failures

Flow works sometimes but fails unpredictably.

### Diagnostic Steps

```
1. Capture the failure
   └── Clear bulletins
   └── Run processor once
   └── Check for new bulletins

2. Compare success vs failure
   └── Inspect FlowFiles that succeeded
   └── Inspect FlowFiles that failed (check failure relationship)

3. Look for patterns
   └── Specific data values?
   └── Time of day?
   └── Volume related?
```

### Tools

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg_id = "<pg-id>"
proc = nipyapi.canvas.get_processor("ProblematicProcessor")

# Clear bulletins to get a clean slate
nipyapi.bulletins.clear_all_bulletins(pg_id=pg_id)

# Run once
nipyapi.canvas.schedule_processor(proc, "RUN_ONCE")

# Check for new bulletins
import time
time.sleep(2)
bulletins = nipyapi.bulletins.get_bulletin_board(pg_id=pg_id)
if bulletins:
    for b in bulletins:
        print(f"[{b.level}] {b.source_name}: {b.message}")

# Check failure relationship for failed FlowFiles
connections = nipyapi.canvas.list_all_connections(pg_id)
failure_conn = next((c for c in connections
                     if c.source_id == proc.id
                     and 'failure' in c.component.selected_relationships), None)
if failure_conn:
    failed_ff = nipyapi.canvas.peek_flowfiles(failure_conn, limit=1)
    if failed_ff:
        print(f"Failed FlowFile attributes: {failed_ff[0].attributes}")
```

---

## Bulletin Errors

Explicit error messages from processors.

### Diagnostic Steps

```
1. Get bulletins
   └── Note source, message, timestamp

2. Match error pattern
   └── Check core-troubleshooting.md

3. If config issue
   └── Check processor/controller properties

4. If connectivity issue
   └── Check network, credentials
```

### Tools

```bash
# Get bulletins
nipyapi --profile <profile> bulletins get_bulletin_board --pg_id "<pg-id>"
```

See `references/ops-bulletins.md` for detailed bulletin investigation.
See `references/core-troubleshooting.md` for error pattern matching.

---

## Slow Throughput

Flow works but slower than expected.

### Diagnostic Steps

```
1. Identify bottleneck
   └── Which connection has growing queue?
   └── Which processor has most active threads?

2. Check processor configuration
   └── Concurrent tasks setting
   └── Batch size
   └── Timeout values

3. Check external systems
   └── Destination capacity
   └── Network latency
```

### Tools

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

# Find connections with growing queues
connections = nipyapi.canvas.list_all_connections(pg_id)
for conn in connections:
    queued = conn.status.aggregate_snapshot.flow_files_queued
    if queued > 100:  # Threshold
        print(f"Potential bottleneck: -> {conn.component.destination.name} ({queued} queued)")

# Check processor concurrency
processors = nipyapi.canvas.list_all_processors(pg_id)
for proc in processors:
    concurrent = proc.component.config.concurrent_tasks_count
    threads = proc.status.aggregate_snapshot.active_thread_count
    print(f"{proc.component.name}: {threads}/{concurrent} threads")
```

---

## Investigation Checklist

Use this checklist to ensure thorough investigation:

- [ ] Captured initial status (`get_status`)
- [ ] Checked bulletins if errors present
- [ ] Identified where data stops (if applicable)
- [ ] Inspected FlowFile attributes at problem point
- [ ] Inspected FlowFile content if needed
- [ ] Checked processor configuration
- [ ] Checked controller service status
- [ ] Documented findings (if using diary)

---

## Tool Reference

| Task | Tool | Reference |
|------|------|-----------|
| Overall health check | `nipyapi ci get_status` | `ops-flow-lifecycle.md` |
| Error messages | `nipyapi bulletins get_bulletin_board` | `ops-bulletins.md` |
| List connections | `nipyapi.canvas.list_all_connections` | `ops-connection-inspection.md` |
| Inspect FlowFiles | `nipyapi.canvas.peek_flowfiles` | `ops-connection-inspection.md` |
| Get FlowFile content | `nipyapi.canvas.get_flowfile_content` | `ops-connection-inspection.md` |
| Run processor once | `nipyapi.canvas.schedule_processor` | `ops-flow-lifecycle.md` |
| Clear bulletins | `nipyapi bulletins clear_all_bulletins` | `ops-bulletins.md` |

---

## Related References

- `references/ops-connection-inspection.md` - Detailed connection and FlowFile inspection
- `references/ops-flow-lifecycle.md` - Start, stop, run-once operations
- `references/ops-bulletins.md` - Bulletin retrieval and analysis
- `references/core-troubleshooting.md` - Error patterns and fixes
- `references/core-investigation-diary.md` - Investigation methodology
