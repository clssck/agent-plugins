# SV Quality Score Formula

Compute the quality score for a semantic view from a single `DESCRIBE SEMANTIC VIEW <fqn>` result.

## How to extract signals

| Signal | How to read from DESCRIBE output |
|--------|----------------------------------|
| Table count | Count rows where `object_kind = 'TABLE'` |
| Has keys | Any TABLE row where `property IN ('PRIMARY_KEY','UNIQUE_KEY')` and `property_value != '[]'` |
| Has relationships | Any row with `object_kind = 'RELATIONSHIP'` — only check if table count > 1 |
| Has metrics | Any row with `object_kind = 'METRIC'` |
| VQR count | Count rows where `object_kind IN ('AI_VERIFIED_QUERY','VERIFIED_QUERY')`. Fallback: parse `verified_queries` array from the `object_kind = 'EXTENSION'` row JSON for older views |
| Avg description chars | Average `LEN(property_value)` across DIMENSION/FACT/METRIC/TABLE rows where `property = 'COMMENT'` and value is non-empty |

## Score formula

```
has_keys          → 1 pt
has_relationships → 1 pt  (only if table_count > 1; N/A for single-table, excluded from denominator)
has_metrics       → 1 pt
vqr_saturation    → 2 × (1 − exp(−(ln10/10) × vqr_count))   max 2 pts, saturates at ~10 VQRs
desc_depth        → 1 × (1 − exp(−(ln100/100) × avg_chars))  max 1 pt, saturates at ~100 chars

max = 7 if table_count > 1, else 6
score = total / max × 100
```

## Thresholds

- >= 70% → Good
- 50–69% → OK (needs work but functional)
- < 50% → Low

## Checklist output format

For multi-table views, show all lines. For single-table views, replace the "Has relationships" line with the N/A line.

```
Quality Score: X/Y (Z%) [Good / OK / Low]

  Has keys          [pass / MISSING → can set primary key]
  Has relationships [pass / MISSING → suggest relationships (multi-table only)]
  Has metrics       [pass / MISSING → suggest metrics & filters]
  VQRs: N           [pass / LOW    → suggest verified queries]
  Descriptions      [pass / SHALLOW → generate descriptions]
```

Single-table variant (replace the relationships line):
```
  Relationships: N/A (single-table view, not scored)
```
