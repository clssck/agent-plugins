# Compliance Regulations Reference

Compact routing aid for common data-protection regulations and how they map to Snowflake policies. This is a pointer, not a substitute for the authoritative sources — follow the linked official source to determine the exact protected fields for a given regulation, then apply the canonical Snowflake patterns below.

## Which regulation applies

| If you have… | And subjects in… | Regulation | Authoritative source (find the exact protected fields here) |
|---|---|---|---|
| Credit / payment card data | Anywhere | **PCI-DSS** | [PCI SSC Document Library](https://docs.pcisecuritystandards.org/) |
| Patient / health data (PHI) | US | **HIPAA** | [HHS Privacy Rule](https://www.hhs.gov/hipaa/for-professionals/privacy/index.html) · [Security Rule](https://www.hhs.gov/hipaa/for-professionals/security/index.html) |
| Personal data | EU | **GDPR** | [gdpr-info.eu](https://gdpr-info.eu/) · [UK ICO guide](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/) |
| Consumer data | California | **CCPA/CPRA** | [CPPA regulations](https://cppa.ca.gov/regulations/) · [CA AG CCPA](https://oag.ca.gov/privacy/ccpa) |
| Financial-reporting data | US (public company) | **SOX** | [SEC SOX overview](https://www.sec.gov/spotlight/sarbanes-oxley.htm) · [PCAOB standards](https://pcaobus.org/oversight/standards/auditing-standards) |
| Student education records | US | **FERPA** | [ED FERPA guidance](https://studentprivacy.ed.gov/ferpa) · [34 CFR Part 99](https://www.ecfr.gov/current/title-34/subtitle-A/part-99) |
| Biometric data | Illinois | **BIPA** | Illinois BIPA statute |
| Children's data (<13) | US | **COPPA** | FTC COPPA rule |

Note: EU employee data → GDPR; regulations stack (e.g. a US healthcare public company handling EU customers may face HIPAA + SOX + GDPR at once).

## Canonical Snowflake patterns

Nearly all of these regulations reduce to two enforcement idioms: **role-gated masking** for column values and **row access** for record scoping. Adapt the authorized role(s), the redaction, and the target columns to the regulation and fields identified from the source above.

```sql
-- Role-gated masking: authorized roles see the value, everyone else gets a redaction.
CREATE MASKING POLICY <reg>_mask AS (val STRING) RETURNS STRING ->
  CASE WHEN IS_ROLE_IN_SESSION('<AUTHORIZED_ROLE>') THEN val
       ELSE '***PROTECTED***' END          -- e.g. PCI: CONCAT('****-****-****-', RIGHT(val,4))
  COMMENT = '<regulation>: restrict <field> to <authorized role>';

-- Row access: restrict rows to an authorized relationship (treating provider, enrolled course, region, …).
CREATE ROW ACCESS POLICY <reg>_row_access AS (key STRING) RETURNS BOOLEAN ->
  IS_ROLE_IN_SESSION('<AUTHORIZED_ROLE>')
  OR EXISTS (SELECT 1 FROM <relationship_table> WHERE <maps CURRENT_USER() to key>);
```

Common variations: PCI shows last 4 digits rather than a full redaction; GDPR/CCPA gate on a region/consent column; HIPAA/FERPA scope rows via a provider/enrollment relationship; SOX masks financial numerics to `NULL` for non-finance/non-auditor roles and often pairs with change tracking.

## Red flags worth checking regardless of regulation

- Sensitive values stored that never should be (e.g. PCI CVV) → delete, don't mask.
- Sensitive columns accessible to non-essential roles → restrict.
- No audit trail / access logging for the protected data → enable.
- No workflow for data-subject / erasure / opt-out requests (GDPR, CCPA) → implement.
- Cross-border transfer without safeguards (GDPR) → document lawful basis / SCCs.
