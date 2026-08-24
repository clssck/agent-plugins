---
name: openflow-author-pattern-files
description: Blueprint for processing files from cloud storage. Load when building flows that read from S3, GCS, or similar.
---

# Pattern: Cloud File Processing

Blueprint for building flows that process files from cloud storage into Snowflake.

**Check first:** Does a file-based Connector exist? Check `connector-main.md` before building custom.

---

## When to Use This Pattern

- Processing files from S3, GCS, Azure Blob, or similar
- Need custom file format handling
- Require file-level transformations before loading
- Complex file naming or partitioning logic
- Snowflake External Stage or direct Snowpipe usage not appropriate

---

## Core Components

| Tool | Purpose | See |
|------|---------|-----|
| `ListS3` / `ListGCSBucket` | List files, track processed | `author-component-selection.md` |
| `FetchS3Object` / `FetchGCSObject` | Download file content | `author-component-selection.md` |
| `ConvertRecord` | Parse file format (CSV, JSON, Avro) | `author-component-selection.md` |
| `SplitRecord` | Split large files into batches | `author-component-selection.md` |
| `UpdateSnowflakeDatabase` | Create/alter table from schema | `author-snowflake-destination.md` |
| `PutSnowpipeStreaming` | Write to Snowflake | `author-snowflake-destination.md` |

---

## Sub-Patterns

<!-- TODO: Detail these sections -->

### List → Fetch Pattern

*To be detailed: why separate list and fetch*

### File Format Detection

*To be detailed: IdentifyMimeType, format-specific readers*

### Large File Handling

*To be detailed: SplitRecord, memory management*

### Partitioned Data

*To be detailed: handling date-partitioned folders*

### File Cleanup

*To be detailed: delete/move after processing*

---

## Related References

- `author-main.md` - Authoring router
- `author-component-selection.md` - Component descriptions
- `nifi-recordpath.md` - Record transformation
- `author-snowflake-destination.md` - Snowflake destination
