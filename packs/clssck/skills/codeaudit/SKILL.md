---
name: codeaudit
description: "Invoke explicitly for offline vulnerability research: white-box source audit, patch diffing, and EDR/ETW/AMSI telemetry reverse engineering. Enumerate attacker-controlled inputs, diff patched and unpatched builds, map telemetry coverage, and prove findings with measured impact in a lab. Live black-box testing belongs to exploitation; surface mapping to api-recon."
disable-model-invocation: true
---

# Code Audit and Binary Research

Three modes share one discipline: establish reachability and attacker control, read the real implementation, and prove the claim in a lab. Source audit traces every input forward to a sink; patch diff recovers the bug from the fix that closed it; endpoint telemetry maps what a defender actually observes.

<directives>

| Mode | Allowed | Boundary |
|---|---|---|
| Source audit | First-party production code, checked-in security configuration | Test code, build scripts, vendored, generated, docs |
| Patch diff | Builds you own or hold under written scope | Running a recovered PoC against unowned systems |
| Endpoint telemetry | Your lab VMs, written-scope hosts, exercise ranges | Vendor binaries or extracted code leaving the lab |

- A candidate is a finding only when it is reachable in production, attacker-controlled data reaches the sink, and the attacker gains a capability they lacked.
- Comment prose, naming, "by design", and "sanitized downstream" satisfy no gate; only read code or observed behavior does.
- A sanitizer whose scope does not match the sink context is itself a candidate.
- Static analysis is `potential`, never confirmed. A missing toolchain is `blocked` with the exact binary named; simulated diff output or invented telemetry is never reported.
- Reports use `{target}`, `{host}`, `{user}` placeholders; real hostnames, IPs, and usernames stay in the lab.

</directives>

<instruction>

| Trigger | Mode | Reference |
|---|---|---|
| Application, plugin, service, or repository source provided or authorized for fetching | Source audit | procedure below |
| CVE with a patch but no PoC, Patch Tuesday triage, backport gap, closed-source security update | Patch diff | [patch diff](skill://codeaudit/references/patch-diff.md) |
| EDR/AV telemetry mapping, hook survey, detection-gap measurement, adversary simulation in a lab | Endpoint telemetry | [endpoint telemetry](skill://codeaudit/references/edr-telemetry.md) |

- Engagement scope, records, and handoff → `pentest-tradecraft`; finding strength and proof basis → [finding quality](skill://pentest-tradecraft/references/finding-quality.md).
- Write to `assessment/` under the task output directory unless the operator names another path. The skill tree is read-only.
- `read` for source ranges; `grep` for symbols and sinks; `find` when the location is unknown; `eval` for call graphs, path sets, and diffs; `glob` for repository shape; `bash` for real binaries and diff toolchains.
- Partition large repositories by module or subgraph; pass paths, not live variables, to workers. One integration owner merges dispositions.

</instruction>

<procedure>

1. **Inventory inputs.** Every user-controllable entry: routes and parameters, headers, cookies, bodies, RPC methods, queue and event consumers, CLI arguments, request-time config, uploads, webhooks, jobs with external input. Record handler `file:line`.
2. **Catalog shared defenses.** Middleware, auth wrappers, sanitizers, ORM bases, validators. Every later trace verifies against the whole codebase, not only its partition.
3. **Trace forward, one class at a time.** Injection, navigation/XSS, authorization and business logic, file operations, deserialization, cryptography, SSRF. Follow through assignments, interpolation, and calls until a sink, a sanitizer, or the boundary.
4. **Apply the gates.** Reachable, attacker-controlled, new capability. A failure is a hardening note with cited evidence.
5. **Verify across the codebase.** Read the shared defense to confirm it blocks the attack; an elimination cites the `file:line` of the defense, the type constraint, or the non-attacker origin.
6. **Prove it.** Prefer executing against a local instance. When impossible, the static trace carries the entry value, `file:line` at every propagation step, the dangerous value at the sink, and the impact; label it `static-analysis-unexecuted`.
7. **Sweep.** Grep the whole codebase for each confirmed root cause; every instance gets its own disposition.
8. **Record.** Inventory, dispositions, sweep table, findings, and the next question.

</procedure>

## Trace rules

- **Never stop at an abstraction boundary.** Router, dispatcher, middleware, strategy selector, or callback forks the trace; each branch concludes.
- **Audit every parameter at an outbound call site.** A scoping parameter (tenant, user, account id) dropped, defaulted, substituted, or widened (`*`, `~`, `-1`, `all`) between validation and the call is a candidate authorization bypass.
- **Exhaust all paths.** An input used three ways is three traces; a safe path clears none of the others.
- **Guards protect only what they validate.** A null check does not constrain injection; match the check to the sink.
- **Follow through stores.** Input written to a database, cache, or queue continues wherever a reader consumes it.
- **Follow through responses.** Input controlling an outbound URL makes the response attacker-influenced; input selecting a resource makes the response mapper a data-exposure candidate.
- **Search callers transitively.** All callers of a sink, then callers of callers, until entry points or exhaustion.
- **Read the sink source before confirming.** Search output navigates; source read judges.

## Deliverables

| File | Content |
|---|---|
| `inventory.json` | Every input, handler location, final disposition |
| `dispositions.jsonl` | Candidate, gate results, cited defense or sink, status |
| `findings.json` | Confirmed findings with PoC, measured impact, proof basis, retest state |
| `sweep.txt` | Root cause, every instance, per-instance disposition |

Zero confirmed findings is valid: deliver the coverage statement — classes hunted, method, surfaces, result. Measured impact carries a denominator; gates and self-check live in the finding-quality reference.

<critical>

Every input ends with an explicit disposition (`confirmed`, `eliminated` with cited evidence, `downgraded`, `not_tested`); silent drops are audit failures. Different entry points, parameters, or privilege levels are separate findings. A finding that cannot be replayed is a lead. Patch-diff and telemetry claims are proven in the lab, with the patched run or the silent telemetry source recorded.

</critical>
