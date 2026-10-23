# Endpoint Defense Telemetry

Map what an endpoint agent monitors, then measure which countermeasure classes defeat which telemetry in an isolated lab. The deliverable is a detection-gap report, not a working intrusion tool.

<critical>

- Your own lab VMs, written-scope hosts, or an exercise range only; a CTF range within its rules.
- No vendor binaries or extracted code leave the lab.
- Simulated alerts or invented detections are never reported as measured.
- The environment needs an authorized Windows lab VM reachable from the task environment. If none exists, report the gap and stop.
- Borrowed public code is read, attributed, and kept minimal before it runs on a lab host.

</critical>

## Surfaces

| Surface | Establish | Measure |
|---|---|---|
| User-mode `ntdll` hooks | Which functions are hooked and by which module | In-memory vs on-disk diff, hook offsets |
| Kernel callbacks | Which callback classes are registered | Callback enumeration, driver inventory |
| ETW | Which providers consume process/image/thread data | Provider presence, events during the run |
| AMSI | Which processes load it and what is scanned | Module load and scan events |

## Classes under test

| Surface | Countermeasure class |
|---|---|
| User-mode `ntdll` hooks | Indirect syscall with dynamic SSN resolution; fresh ntdll copy; hardware-breakpoint redirection |
| Kernel callbacks | Call-stack spoofing; routing through legitimate trigger chains |
| ETW | Provider teardown; event-write head patch |
| AMSI | Scan-buffer patch; clean amsi copy; hardware-breakpoint redirection |

## Workflow

1. **Identify defenses.** Enumerate endpoint services, filter drivers, Sysmon presence, and loaded agent DLLs with versions:

   ```powershell
   Get-Service | Where-Object {$_.Name -match 'CSAgent|SentinelAgent|elasticendpoint|MsMpEng|sysmon'}
   fltmc filters
   ```

   This inventory is the baseline artifact.
2. **Survey hooks.** Dump in-memory `ntdll.dll` `.text` from a process carrying the agent DLL, diff against disk, record divergences. `pe-sieve64.exe /pid <pid> /shellc 3 /modules 3 /dir hooks_dump` automates the sweep; manual dump-diff is the fallback.
3. **Map kernel and provider surfaces.** Callbacks via kernel debugging or a driver-inspection tool; ETW providers; AMSI loads.
4. **Select one countermeasure class per surface.** State the surface and the class under test; ordering matters because silencing one source can generate an alert.
5. **Implement in the lab harness.** Minimal, lab-specific code; record exact commits of public references (SysWhispers, Hell's Gate/Halo's Gate, Ekko) and read them before use.
6. **Measure.** Baseline run, then the harness; record every alert source that fires and every one that stays silent. Negative results are results.
7. **Map and report.** Attribute detections to telemetry source and ATT&CK (T1562.001, T1562.006, T1055, T1027 as applicable); hand the owner a gap list with reproduction steps.

## Tools

| Tool | Use | Verify |
|---|---|---|
| `pe-sieve` | In-memory hook and injection survey | Binary present in the lab |
| Sysmon | Telemetry baseline and event IDs 1/7/8/10 | Service installed and configured |
| windbg plus IDA/Ghidra | Callback enumeration, agent DLL/driver analysis | Symbols and toolchain available |
| SysWhispers3 | Syscall stub generation for the class under test | Reference read and attributed |
| API Monitor | Dynamic API observation | Manual install in the lab |

- Modern agents treat ETW plus kernel callbacks as primary; user-mode unhooking alone is a dated answer and never reported as comprehensive coverage.
- Product evaluation keeps vendor binaries in the lab; describe behavior and gaps, not extracted code.
- Verify tool availability before promising a step; a missing tool is a recorded blocker.

## Deliverables

`baseline.json` (services, filters, callbacks, providers, versions), `hooks/` (dumps and offsets), `experiments.jsonl` (surface, class, sequence, alerts fired/silent), `report.md` (gaps, ATT&CK mapping, reproduction, limitations). Every technique run has an observation naming its telemetry source.
