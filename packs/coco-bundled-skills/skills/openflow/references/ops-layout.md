---
name: openflow-ops-layout
description: Canvas layout and component positioning for Openflow/NiFi. Covers building new flows, organizing existing flows, and process group management.
---

# Canvas Layout

Intelligent positioning and organization of components on the NiFi canvas using `nipyapi.layout`.

**Note:** Layout operations modify service state. Apply the Check-Act-Check pattern (see `references/core-guidelines.md`).

## Scope

- Canvas positioning and component organization
- Building new flows with proper layout
- Process group placement on root canvas

**Note:** Automatic layout works well for simple flows but only partially solves complex cases.

## Coordinate System

**All component positions are top-left corner coordinates.**

| Component | Width | Height | Center Offset (under processor) |
|-----------|-------|--------|--------------------------------|
| Processor | 352px | 128px | - |
| Port | 240px | 48px | 56px (`PORT_CENTER_OFFSET`) |
| Funnel | 48px | 48px | 152px (`FUNNEL_CENTER_OFFSET`) |
| Process Group | 384px | 176px | - |
| Queue Box | 224px | 56px | - |

**Centering formula**: To center component A under component B:
```python
offset = (B_width - A_width) / 2
A_x = B_x + offset
```

Use `below(comp, align="center")` for funnels, `align="center_port"` for ports.

---

## Connection Bends and Queue Boxes

Queue information boxes appear **centered over the last bend point** of a connection.

**For parallel paths merging to a funnel:**
- Use **single bends** below center of each source processor
- Each queue box sits on its own vertical segment
- Connection draws diagonal from bend to funnel

```python
# Single bend per connection - avoids queue box overlap
bend = nipyapi.nifi.PositionDTO(x=source_center_x, y=bend_row_y)
conn.component.bends = [bend]
nipyapi.nifi.ConnectionsApi().update_connection(body=conn, id=conn.id)
```

**Anti-pattern**: The only or last bend point of any connection should not overlap, or the information boxes will be obscured.

---

## Approach

Layout operations are often more complex than single CLI commands - consider writing a Python script rather than using the CLI directly.

**When writing scripts:** Remember to activate your profile at the start (see `references/core-session-cli.md` for profile selection):

```python
import nipyapi
import nipyapi.layout as layout

nipyapi.profiles.switch('<profile>')
```

---

## Scenario 1: Building a New Flow

Create a process group in the correct grid position, then build the flow inside it.

### Create Process Group in Grid Position

```python
# Find next available grid slot on root canvas
pg_pos = layout.suggest_pg_position("root")

# Create the process group (parent_pg accepts string ID or entity)
pg = nipyapi.canvas.create_process_group("root", "My Flow", location=pg_pos)
```

### Start Flow at Default Origin

```python
proc_type = nipyapi.canvas.get_processor_type("GenerateFlowFile")

# First component at default origin (400, 400) inside the PG
first_pos = layout.new_flow()
proc1 = nipyapi.canvas.create_processor(pg, proc_type,
    location=first_pos, name="Ingest")
```

### Build Vertically (Main Path)

```python
proc2 = nipyapi.canvas.create_processor(pg, proc_type,
    location=layout.below(proc1), name="Validate")

proc3 = nipyapi.canvas.create_processor(pg, proc_type,
    location=layout.below(proc2), name="Transform")

nipyapi.canvas.create_connection(proc1, proc2, ['success'])
nipyapi.canvas.create_connection(proc2, proc3, ['success'])
```

### Add Side Branches (Forks)

```python
# Fork for error handling - diagonal right and down
error_proc = nipyapi.canvas.create_processor(pg, proc_type,
    location=layout.fork(proc2, direction="right"), name="HandleError")

nipyapi.canvas.create_connection(proc2, error_proc, ['failure'])

# Continue branch downward
log_error = nipyapi.canvas.create_processor(pg, proc_type,
    location=layout.below(error_proc), name="LogError")

nipyapi.canvas.create_connection(error_proc, log_error, ['success'])
```

### Center Smaller Components

```python
# Funnels and ports are smaller - center them under processors
funnel = nipyapi.canvas.create_funnel(pg.id,
    position=layout.below(proc3, align="center"))

input_port = nipyapi.canvas.create_input_port(pg.id,
    port_name="Input",
    position=layout.above(proc1, align="center_port"))
```

---

## Scenario 2: Tidying an Existing Messy Flow

**Before making changes:** Ask the user if they want to commit the current state to version control first. Layout changes cannot be undone except by reverting.

### Step 1: Analyze the Flow

```python
pg = nipyapi.canvas.get_process_group("Messy Flow")

# Find main spine (longest forward path)
spine = layout.find_flow_spine(pg.id)
print(f"Spine: {len(spine)} components")

# Find all branches recursively
branches = layout.get_side_branches(pg.id, spine, recursive=True)
print(f"Branch points: {len(branches)}")
```

### Step 2: Clear Old Bends

```python
# Clear all bends (self-loop bends are preserved by default)
cleared = layout.clear_flow_bends(pg.id)
print(f"Cleared bends from {cleared} connections")
```

### Step 3: Apply Automatic Layout

```python
plan = layout.suggest_flow_layout(pg.id)

flow = nipyapi.canvas.get_flow(pg.id)
id_to_comp = {p.id: p for p in flow.process_group_flow.flow.processors}
id_to_comp.update({f.id: f for f in flow.process_group_flow.flow.funnels})

for item in plan['spine'] + plan['branches']:
    comp = id_to_comp.get(item['id'])
    if comp:
        layout.move_component(comp, item['position'])
```

### Step 4: Post-Layout Adjustments

Check visually for:

1. **Overlapping terminals** - Nudge to the right:
   ```python
   layout.move_component(comp, layout.right_of(comp))
   ```

2. **Feedback loops crossing layout** - Add bends for clean routing

---

## Scenario 3: Adding to an Existing Flow

### Find Component by Name

```python
target_proc = nipyapi.canvas.get_processor("Transform")
new_proc = nipyapi.canvas.create_processor(pg, proc_type,
    location=layout.below(target_proc), name="Enrich")
nipyapi.canvas.create_connection(target_proc, new_proc, ['success'])
```

### Find by Position (Bottom-most)

```python
flow = nipyapi.canvas.get_flow(pg.id)
processors = flow.process_group_flow.flow.processors
bottom_proc = max(processors, key=lambda p: p.position.y)

new_proc = nipyapi.canvas.create_processor(pg, proc_type,
    location=layout.below(bottom_proc), name="NewStep")
nipyapi.canvas.create_connection(bottom_proc, new_proc, ['success'])
```

### Adding a Side Branch

```python
side_proc = nipyapi.canvas.create_processor(pg, proc_type,
    location=layout.fork(target_proc, direction="right"), name="HandleError")
nipyapi.canvas.create_connection(target_proc, side_proc, ['failure'])
```

### Loop-Back Connections

When connecting back to an earlier processor (retry logic, pagination), route **left around the spine** with right-angle bends:

```python
# Loop from CheckHasNext back up to FetchPage
loop_conn = nipyapi.canvas.create_connection(
    check_proc, fetch_proc,
    relationships=['HasNext'],
    bends=[
        (fetch_proc.position.x - 200, check_proc.position.y),  # Left of source
        (fetch_proc.position.x - 200, fetch_proc.position.y)   # Up to target level
    ]
)
```

**Result:** Clean left-side routing that doesn't cross the main flow spine.

---

## Scenario 4: Organizing Process Groups

### Arrange into Grid

```python
root_id = nipyapi.canvas.get_root_pg_id()

# Square-ish grid, sorted alphabetically
layout.align_pg_grid(root_id, sort_by_name=True)

# Or specify columns
layout.align_pg_grid(root_id, columns=4)
```

---

## Scenario 5: Fan-In Connections to Collector PG

When multiple PGs on a spine send outputs to a single collector PG (e.g., logging), queue boxes overlap unless properly staggered.

**Checklist (ALL steps required):**
- [ ] Step 1: Collector PG positioned (centered vertically, offset right)
- [ ] Step 2: Bend positions calculated for each connection
- [ ] Step 3: Bends applied to all fan-in connections

Skipping Steps 2-3 results in overlapping queue boxes.

### Step 1: Position the Collector PG (Centered)

Place the collector vertically centered relative to the spine, offset to the right to leave room for queue boxes:

```python
PROCESS_GROUP_WIDTH = 384
PORT_QUEUE_BOX_WIDTH = 240
GRID_SIZE = 8
PADDING = GRID_SIZE * 2  # 16px

# Calculate vertical midpoint of spine
first_spine_y = spine_pgs[0].position.y      # e.g., 100
last_spine_y = spine_pgs[-1].position.y      # e.g., 1000
midpoint_y = (first_spine_y + last_spine_y) / 2  # e.g., 550

# Position collector: right of queue boxes, vertically centered
# Leave space for 2 queue boxes (success + failure) plus padding
spine_x = spine_pgs[0].position.x  # e.g., 100
collector_x = spine_x + PROCESS_GROUP_WIDTH + (2 * PORT_QUEUE_BOX_WIDTH) - 100  # ~576
collector_y = midpoint_y + 10  # Slight offset for visual balance

nipyapi.canvas.update_process_group(
    collector_pg,
    update={"position": {"x": collector_x, "y": collector_y}}
)
```

### Step 2: Calculate Staggered Bend Positions

For each source PG, spread queue boxes horizontally with padding:

```python
def get_bend_x(pg_x, connection_index):
    """Calculate x position for nth connection from a PG."""
    first_x = pg_x + PROCESS_GROUP_WIDTH + (PORT_QUEUE_BOX_WIDTH // 2) + PADDING
    return first_x + (connection_index * (PORT_QUEUE_BOX_WIDTH + PADDING))

# Example for spine at x=100:
# - success (idx=0): bend_x = 100 + 384 + 120 + 16 = 620
# - failure (idx=1): bend_x = 620 + 256 = 876
```

### Step 3: Apply Bends to Fan-In Connections

```python
for source_pg in spine_pgs:
    connections = get_connections_to_collector(source_pg, collector_pg)
    # Sort: success first, failure last
    connections.sort(key=lambda c: (c.source.name == "failure", c.source.name))

    for idx, conn in enumerate(connections):
        bend_x = get_bend_x(source_pg.position.x, idx)
        bend_y = source_pg.position.y + 100  # Slightly below PG top

        conn_entity = nipyapi.nifi.ConnectionsApi().get_connection(conn.id)
        conn_entity.component.bends = [
            nipyapi.nifi.PositionDTO(x=bend_x, y=bend_y)
        ]
        nipyapi.nifi.ConnectionsApi().update_connection(id=conn.id, body=conn_entity)
```

**Result:** Collector PG is vertically centered. Queue boxes are horizontally staggered at each source PG's level. Connection lines converge diagonally to the central collector, creating a clean fan-in pattern.

---

## Scenario 6: De-overlapping Separate Flows

### Identify Components from Each Flow

```python
flow1_proc = nipyapi.canvas.get_processor("Ingest_CustomerData")
flow2_proc = nipyapi.canvas.get_processor("Ingest_OrderData")
```

### Get All Connected Components and Connections

```python
# get_flow_components returns a FlowSubgraph with components and connections
flow1 = nipyapi.canvas.get_flow_components(flow1_proc)
flow2 = nipyapi.canvas.get_flow_components(flow2_proc)
```

### Calculate Separation and Transpose

```python
flow1_bounds = layout.get_canvas_bounds(components=flow1.components)
flow2_bounds = layout.get_canvas_bounds(components=flow2.components)

offset_x = (flow1_bounds['max_x'] + layout.BLOCK_WIDTH) - flow2_bounds['min_x']

# Pass connections for efficient bend handling (avoids extra API calls)
layout.transpose_flow(flow2.components, offset=(offset_x, 0), connections=flow2.connections)
```

---

## Function Reference

### Positioning Functions

| Function | Purpose | Returns |
|----------|---------|---------|
| `new_flow()` | Starting position for new flow | `(400, 400)` |
| `below(comp, align="aligned")` | Position below component | `(x, y)` |
| `above(comp)` | Position above component | `(x, y)` |
| `right_of(comp)` | Position to the right | `(x, y)` |
| `left_of(comp)` | Position to the left | `(x, y)` |
| `fork(comp, direction="right")` | Diagonal fork position | `(x, y)` |
| `grid_position(row, col)` | Position in grid layout | `(x, y)` |

**Align options:** `"aligned"` (default), `"center"` (for funnels), `"center_port"` (for ports)

### Movement Functions

| Function | Purpose |
|----------|---------|
| `move_component(comp, pos)` | Move any component (handles self-loop bends) |
| `transpose_flow(components, offset, connections)` | Move entire flow preserving shape and bends |
| `clear_flow_bends(pg_id)` | Clear all bends in a PG (preserves self-loops) |

### Connection Functions

| Function | Purpose |
|----------|---------|
| `canvas.get_connection(id)` | Get a connection by ID |
| `canvas.update_connection(conn, name, bends)` | Update connection name or bends |
| `canvas.get_flow_components(proc)` | Get flow subgraph (components + connections) |

### Analysis Functions

| Function | Purpose |
|----------|---------|
| `find_flow_spine(pg_id)` | Find longest forward path through flow |
| `get_side_branches(pg_id, spine)` | Find all branches recursively |
| `get_canvas_bounds(pg_id)` | Get bounding box of components |
| `suggest_flow_layout(pg_id)` | Generate complete layout plan |

### Process Group Grid

| Function | Purpose |
|----------|---------|
| `align_pg_grid(pg_id, sort_by_name=True)` | Arrange PGs into grid |
| `suggest_pg_position(pg_id)` | Find next available grid slot |

---

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `BLOCK_WIDTH` | 400px | Horizontal spacing between components |
| `BLOCK_HEIGHT` | 200px | Vertical spacing between components |
| `FORK_SPACING` | 640px | Diagonal fork spacing |
| `PROCESSOR_WIDTH` | 352px | Processor box width |
| `PROCESSOR_HEIGHT` | 128px | Processor box height |
| `PROCESS_GROUP_WIDTH` | 384px | Process group width |
| `PORT_WIDTH` | 240px | Input/output port width |
| `PORT_HEIGHT` | 48px | Port height |
| `PORT_CENTER_OFFSET` | 56px | X offset to center port under processor |
| `FUNNEL_WIDTH` | 48px | Funnel width |
| `FUNNEL_HEIGHT` | 48px | Funnel height |
| `FUNNEL_CENTER_OFFSET` | 152px | X offset to center funnel under processor |
| `QUEUE_BOX_WIDTH` | 224px | Queue label box (processor-to-processor) |
| `QUEUE_BOX_HEIGHT` | 56px | Queue label box height |
| `PORT_QUEUE_BOX_WIDTH` | 240px | Queue label box (port-to-port between PGs) |
| `GRID_SIZE` | 8px | NiFi UI snap grid |
| `DEFAULT_ORIGIN` | (400, 400) | New flow starting position |

---

## Known Limitations

### What Works Well
- Linear flows with clear main path
- Single level of branching
- Flows with 5-15 components
- Process group grid organization

### What Requires Manual Adjustment
1. **Terminal overlaps** - Multiple branches ending at same depth
2. **Feedback loop routing** - Retry connections create diagonal lines
3. **Queue box collisions** - Connection labels not collision-detected
4. **Nested branches** - Branches of branches may not space correctly
5. **Large flows (20+ components)** - Increasing complexity reduces effectiveness

### Recommended Workflow
1. **Simple flows:** `suggest_flow_layout()` may fully organize
2. **Complex flows:** Treat auto-layout as ~70% solution, then:
   - Visual inspection in NiFi UI
   - Nudge overlapping components
   - Add bends to feedback loops manually

---

## Best Practices

1. **Build new flows correctly from the start** - Use relative positioning
2. **Use process groups** - Organize related components
3. **Visual verification** - Review in UI after automatic layout
4. **Clear bends before reorganizing** - Use `layout.clear_flow_bends(pg.id)`
5. **Commit before tidying** - Layout changes can't be undone without version control
6. **Use get_flow_components for transpose** - Pass connections for efficient bend handling
7. **Refresh objects after moves** - After calling `move_component()`, re-fetch the object before using it for relative positioning (e.g., `layout.below()`). The original object retains stale coordinates.

## Related References

- `references/ops-version-control.md` - Commit before making layout changes
- `references/ops-tracked-modifications.md` - Layout changes are tracked modifications
