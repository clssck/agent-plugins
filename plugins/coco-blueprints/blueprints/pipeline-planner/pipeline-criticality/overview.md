## Pipeline Criticality

How critical is this pipeline to your organization? This determines the depth of testing, monitoring, and validation that will be generated in the implementation plan.

### Why This Matters

Criticality drives the testing and monitoring strategy without requiring you to specify individual test categories. The plan generator uses your answer to determine:

- **Scope of automated tests** (uniqueness, completeness, stability, referential integrity, etc.)
- **Monitoring and alerting depth** (what triggers alerts, at what severity)
- **Validation rigor** (statistical stability checks, day-over-day variance thresholds)


### Configuration Questions

#### How critical is this pipeline to your organization? (`pipeline_criticality`: single-select)
Select the criticality tier that best describes this pipeline's role.
This determines the depth of automated testing, monitoring, and validation
generated in your implementation plan.

- **Mission-critical**: Revenue-impacting, SLA-bound, or feeds downstream
  production systems. Generates comprehensive test suite (structural integrity,
  referential integrity, statistical stability, enum validity, downstream
  compatibility, monitoring with severity levels and recovery actions).
- **Important**: Supports key business processes but outages are tolerable
  short-term. Generates standard test suite (uniqueness, completeness,
  row count stability, basic monitoring alerts).
- **Exploratory**: Ad-hoc analysis, prototypes, or internal tooling with no
  SLA. Generates minimal tests (primary key uniqueness, key non-null constraints).

**Options:**
- Mission-critical
- Important
- Exploratory
