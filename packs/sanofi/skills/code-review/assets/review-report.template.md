## Code Review: {change_title}

**Scope:** {file_count} files changed ({lines_added} additions, {lines_removed} deletions)
**Diff mode:** {diff_mode} (uncommitted | commit | range | branch vs base | PR) | **Base:** `{base_ref}` | **Date:** {date}
**Project conventions:** {conventions_source}
**Sanofi baseline applied:** {baseline_applied}

### Verdict: {verdict}

{overview}

### Stats

| Axis | Status |
|------|--------|
| Correctness | {correctness_status} |
| Readability | {readability_status} |
| Architecture | {architecture_status} |
| Security | {security_status} |
| Performance | {performance_status} |

### Critical Issues ({critical_count})

{critical_issues}

### Important Issues ({important_count})

{important_issues}

### Other Findings ({other_count})

{other_findings}

<!-- Optional: include only when a strength provides useful technical evidence. -->
{optional_strengths}

### Verification

- Tests reviewed: {tests_reviewed}
- Commands run (read-only): {commands_run}
- Security checked: {security_checked}
- Project conventions checked: {conventions_checked}
