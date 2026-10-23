# External Breadth (bbot)

Use bbot when breadth matters more than request control: every discovery becomes an event and seeds the next module. Keep single-purpose tools (subfinder, httpx, katana, ffuf, nuclei) for exact requests. Verify `bbot --version` and the live module table before planning; a missing binary is a blocker unless the operator authorizes `uv tool install bbot`.

## Boundaries

- Targets and seeds stay inside the recorded scope. Third-party sources are queried about the target, never exploited.
- Derive the mode from program policy: scanner bans or limits at or below 5 req/s mean passive only; active requires permission; loud families require explicit permission.
- In-scope targets go in `-t`, exclusions in `-b`; `--strict-scope` when subdomains are not implicitly in scope. Events with `scope_distance > 0` are intel, never probe targets.
- Keyless modules by default. A vault key goes into a private YAML config created for the run and passed as `-c <file>`; never on the command line, in output, or in the transcript. Delete the file after the scan.
- Never run the `kitchen-sink` preset against a live target.
- A bbot `FINDING` is a lead, not proof.

## Modes and modules

| Mode | When | Modules |
|---|---|---|
| P — passive | Scanners banned, strict rate limit, zero-touch | `crt`, `crt_db`, `certspotter`, `dnsdumpster`, `hackertarget`, `anubisdb`, `rapiddns`, `subdomaincenter`, `urlscan`, `myssl`, `wayback`, `asn`, `shodan_idb`, `ipneighbor`; email family |
| A — active-safe | Active scanning permitted | P plus `dnsresolve`, `dnscommonsrv`, `baddns*`, `sslcert`, `robots`, `securitytxt`, `oauth`, `graphql_introspection`, `fingerprintx`, `reflected_parameters`, `retirejs`, `badsecrets`, `iis_shortnames`, `filedownload`, `newsletters`, `hunt`, capped spider |
| Loud | Explicit permission only | `paramminer_*`, `virtualhost`, `waf_bypass`, `bypass403`, `dnsbrute*`, `portscan`, `lightfuzz`, `nuclei`, `legba`, `medusa`, `host_header`, `url_manipulation`, `generic_ssrf` |

Mode P runs with seeds only (`-s`, no `-t`) so no module contacts the target. Never mix passive and active modules in one run.

## Recipes

```bash
# passive subdomains
bbot -s example.com -m crt,crt_db,certspotter,dnsdumpster,hackertarget,anubisdb,rapiddns,subdomaincenter,urlscan -n passive-subdoms
# archived URLs
bbot -s example.com -m wayback -n wayback-urls
# IP/ASN enrichment
bbot -s 203.0.113.0/24 -m shodan_idb,ipneighbor,asn -n ip-enrich
# takeover pass
bbot -t example.com -p baddns-heavy -n takeover
# email perimeter
bbot -s example.com -m dnscaa,dnstlsrpt,emailformat,pgp,skymem -n emails
# single-host deep look
bbot -t host.example.com -m sslcert,robots,securitytxt,oauth,graphql_introspection,iis_shortnames -n host-deep
```

Exclusions go in `-b`, for example `-b logout.example.com -b /auth/,/logout` when policy forbids touching session endpoints. Standard tail: `-om json,txt -o <out> -n <scan-name> -y --no-deps`. Module dependencies are expected preinstalled; a module reporting a missing dependency is recorded unavailable, not installed at scan time. Rate control: fewer modules per scan, `--exclude-cdn`, an honest user agent, capped spider (`-c spider_distance=1 spider_depth=2`) on sensitive programs. Split into two passive scans rather than one broad active scan when uncertain.

## Ingestion

Read `<out>/<scan-name>/output.json` per line; `scan.log` and `error.log` are the audit trail. Fields: `type`, `data`, `host`, `resolved_hosts`, `tags`, `module`, `scope_description`, `scope_distance`, `timestamp`.

| Event | Record as |
|---|---|
| `DNS_NAME`, `IP_ADDRESS`, `OPEN_TCP_PORT`, `URL` | Facts with source tags (waf, cdn, cloudflare) |
| `FINDING`, `VULNERABILITY` | Candidates with module and scan id; verify independently |
| `EMAIL_ADDRESS` | Intel facts |

If `error.log` shows a module failed, retry once without it instead of widening the scan. Every fact names its scan id and output path.
