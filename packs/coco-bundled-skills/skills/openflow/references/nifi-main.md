---
name: openflow-nifi-main
description: Apache NiFi tool knowledge router. Load when working with NiFi components, properties, or concepts. Routes to specific NiFi reference material.
---

# NiFi Reference Router

Apache NiFi tool knowledge. Load this when configuring processors, working with FlowFile attributes, or needing NiFi concepts.

**Scope:** NiFi as a tool - syntax, functions, concepts. For Openflow service operations (deploy, start, stop), see `core-guidelines.md` and `ops-*.md` references.

---

## Quick Concepts

**FlowFile**: A piece of data in NiFi with two parts:
- **Content**: The actual data (bytes)
- **Attributes**: Key-value metadata (e.g., `filename`, `uuid`, `path`)

**Expression Language (EL)**: Manipulates FlowFile **attributes** using `${attribute:function()}` syntax. Used in processor properties.

**RecordPath**: Navigates **record content** (JSON, Avro, CSV fields) using `/field/path` syntax. Used in record-aware processors.

**Controller Service**: Shared configuration (e.g., database connections, record readers/writers) used by multiple processors.

---

## Intent Routing

| If you need to... | Load |
|-------------------|------|
| Manipulate FlowFile attributes (EL syntax) | `nifi-expression-language.md` |
| Navigate/transform record fields (JSON, Avro, CSV) | `nifi-recordpath.md` |
| Format dates, parse timestamps, epoch conversion | `nifi-date-formatting.md` |
| Understand FlowFile lifecycle, connections, backpressure | `nifi-concepts.md` |
| Find official NiFi documentation links | `nifi-concepts.md` (has doc links) |

---

## When to Use EL vs RecordPath

| Scenario | Use |
|----------|-----|
| Set/read FlowFile attribute | Expression Language |
| Route based on attribute value | Expression Language |
| Transform field inside JSON/Avro/CSV content | RecordPath |
| Extract nested field from record | RecordPath |
| Format current timestamp for filename | Expression Language (`${now():format(...)}`) |
| Convert date field inside record | RecordPath (`format(toDate(/field, ...), ...)`) |

**Key insight**: EL operates on the FlowFile envelope (attributes). RecordPath operates inside the FlowFile content, assuming it is record orientated.

---

## Processor States

| State | Description |
|-------|-------------|
| `RUNNING` | Actively processing FlowFiles |
| `STOPPED` | Not processing, can be started |
| `DISABLED` | Cannot be started until enabled |
| `INVALID` | Configuration errors prevent running |
| `RUN_ONCE` | Execute one scheduling cycle, then stop |

See `ops-flow-lifecycle.md` for state transitions.

---

## Finding Processor Documentation

### Programmatic Access

```bash
# Get processor documentation by name
nipyapi --profile <profile> canvas get_processor_docs --processor UpdateRecord
```

For Python usage:

```python
docs = nipyapi.canvas.get_processor_docs("UpdateRecord")
print(docs.type_description, docs.tags)
```

### Official Documentation

Processor docs: `https://nifi.apache.org/components/` (NiFi 2.x)

Common bundles:
- `nifi-standard-nar`: GenerateFlowFile, UpdateAttribute, RouteOnAttribute, UpdateRecord
- `nifi-record-serialization-services-nar`: JsonTreeReader, JsonRecordSetWriter, AvroReader
- `nifi-aws-nar`: S3, Kinesis, Lambda processors

---

## Related References

- `nifi-expression-language.md` - EL syntax and functions
- `nifi-recordpath.md` - RecordPath syntax and functions
- `nifi-date-formatting.md` - Date/time patterns
- `nifi-concepts.md` - Architecture concepts
- `author-main.md` - Flow authoring patterns
