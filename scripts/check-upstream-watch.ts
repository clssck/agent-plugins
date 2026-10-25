#!/usr/bin/env bun
// Watches upstream repositories whose content is vendored here as first-party files. It never syncs anything:
// a change opens (or refreshes) one assigned issue per source so a maintainer can review and port it by hand.

import * as path from "node:path";
import { githubGraphql, githubRepositoryField } from "./github";

export interface WatchSource {
  name: string;
  repository: string;
  ref: string;
  path: string;
  reviewedCommit: string;
  target: string;
  issueTitle: string;
}

export interface WatchConfig {
  repository: string;
  assignee: string;
  sources: WatchSource[];
}

/** What upstream looks like for one source. Both values are the latest commit touching `path`. */
export interface SourceState {
  /** Latest commit touching the path on `ref`. */
  latest: string;
  /** Latest commit touching the path as of `reviewedCommit`; equal to `latest` when the path is unchanged since review. */
  reviewed: string;
}

export interface Issue {
  number: number;
  title: string;
  body: string | null;
  state: "open" | "closed";
  /** Null when the author account was deleted. */
  user: { login: string } | null;
  pull_request?: unknown;
}

/** Process environment fields that decide whether this run may write issues. */
export type NotifyEnv = Record<string, string | undefined>;

export type Request = (endpoint: string, init: RequestInit, allowed: number[]) => Promise<unknown>;

const CONFIG_PATH = path.resolve(import.meta.dir, "..", "upstream-watch.json");

const ISSUES_PER_PAGE = 100;
const RESOLVED_MARKER = "<!-- upstream-watch-resolved -->";
const DRIFT_MARKER_LINE = /^<!-- upstream-watch-current:[0-9a-f]+ -->[ \t]*$/gm;
const DRIFT_MARKER = /<!-- upstream-watch-current:[0-9a-f]+ -->/;
const REPOSITORY_SLUG = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const COMMIT_SHA = /^[0-9a-f]{40}$/;
/** Login GitHub records as the author of issues created with the workflow's `github.token`. */
export const NOTIFICATION_AUTHOR = "github-actions[bot]";
/** Stable hidden marker in every body this automation writes; unlike the drift markers it never changes. */
export const OWNERSHIP_MARKER = "<!-- agent-plugins:upstream-watch-notification -->";
const NOTIFY_REF = "refs/heads/main";

async function rest(endpoint: string, init: RequestInit, allowed: number[]): Promise<unknown> {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    throw new Error("GITHUB_TOKEN is required");
  }
  const response = await fetch(`https://api.github.com${endpoint}`, {
    ...init,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "User-Agent": "clssck-agent-plugins",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (!allowed.includes(response.status)) {
    throw new Error(`GitHub REST ${response.status} for ${endpoint}: ${await response.text()}`);
  }
  const data: unknown = await response.json();
  return data;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isIssue(value: unknown): value is Issue {
  if (!isRecord(value)) {
    return false;
  }
  const { user } = value;
  return (
    typeof value.number === "number" &&
    typeof value.title === "string" &&
    (typeof value.body === "string" || value.body === null) &&
    (value.state === "open" || value.state === "closed") &&
    (user === null || (isRecord(user) && typeof user.login === "string"))
  );
}

function requireString(owner: object, key: string, where: string): string {
  const value: unknown = Reflect.get(owner, key);
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Invalid upstream watch config: ${where}.${key} must be a non-empty string`);
  }
  return value;
}

function requireRelativePath(value: string, where: string): void {
  if (
    value.startsWith("/") ||
    value.split("/").some((segment) => segment === ".." || segment === "")
  ) {
    throw new Error(
      `Invalid upstream watch config: ${where} must be a repository-relative path without empty or ".." segments`,
    );
  }
}

/** Validate the parsed config file. Throws on the first defect; the returned value is the same object, typed. */
export function parseConfig(raw: unknown): WatchConfig {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new Error("Invalid upstream watch config: expected an object");
  }
  const repository = requireString(raw, "repository", "config");
  if (!REPOSITORY_SLUG.test(repository)) {
    throw new Error(
      `Invalid upstream watch config: config.repository must be owner/name, got ${repository}`,
    );
  }
  const assignee = requireString(raw, "assignee", "config");
  const rawSources: unknown = Reflect.get(raw, "sources");
  if (!Array.isArray(rawSources) || rawSources.length === 0) {
    throw new Error("Invalid upstream watch config: config.sources must be a non-empty array");
  }

  const names = new Set<string>();
  const titles = new Set<string>();
  const sources = rawSources.map((entry: unknown, index: number): WatchSource => {
    const where = `sources[${index}]`;
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error(`Invalid upstream watch config: ${where} must be an object`);
    }
    const source: WatchSource = {
      name: requireString(entry, "name", where),
      repository: requireString(entry, "repository", where),
      ref: requireString(entry, "ref", where),
      path: requireString(entry, "path", where),
      reviewedCommit: requireString(entry, "reviewedCommit", where),
      target: requireString(entry, "target", where),
      issueTitle: requireString(entry, "issueTitle", where),
    };
    if (!REPOSITORY_SLUG.test(source.repository)) {
      throw new Error(
        `Invalid upstream watch config: ${where}.repository must be owner/name, got ${source.repository}`,
      );
    }
    if (!COMMIT_SHA.test(source.reviewedCommit)) {
      throw new Error(
        `Invalid upstream watch config: ${where}.reviewedCommit must be a 40-character lowercase hex SHA`,
      );
    }
    requireRelativePath(source.path, `${where}.path`);
    requireRelativePath(source.target, `${where}.target`);
    if (names.has(source.name)) {
      throw new Error(`Invalid upstream watch config: duplicate source name ${source.name}`);
    }
    if (titles.has(source.issueTitle)) {
      throw new Error(`Invalid upstream watch config: duplicate issueTitle ${source.issueTitle}`);
    }
    names.add(source.name);
    titles.add(source.issueTitle);
    return source;
  });
  return { repository, assignee, sources };
}

function historyQuery(sourcePath: string): string {
  return `... on Commit { history(first: 1, path: ${JSON.stringify(sourcePath)}) { nodes { oid } } }`;
}

/** `repo.<key>.history.nodes[0].oid` of one aliased repository field, or undefined when any step is missing. */
function firstOid(repo: unknown, key: "head" | "reviewed"): string | undefined {
  const object = isRecord(repo) ? repo[key] : undefined;
  const history = isRecord(object) ? object.history : undefined;
  const nodes = isRecord(history) ? history.nodes : undefined;
  const node: unknown = Array.isArray(nodes) ? nodes[0] : undefined;
  const oid = isRecord(node) ? node.oid : undefined;
  return typeof oid === "string" ? oid : undefined;
}

/** Fetch, per source, the latest commit touching the watched path on its ref and as of the reviewed commit. */
export async function fetchStates(
  sources: WatchSource[],
  graphql: (query: string) => Promise<unknown> = githubGraphql,
): Promise<SourceState[]> {
  const fields = sources.map(
    (source, index) =>
      `s${index}: ${githubRepositoryField(source.repository)} { ` +
      `head: object(expression: ${JSON.stringify(source.ref)}) { ${historyQuery(source.path)} } ` +
      `reviewed: object(oid: ${JSON.stringify(source.reviewedCommit)}) { ${historyQuery(source.path)} } }`,
  );
  const data = await graphql(`query { ${fields.join(" ")} }`);
  return sources.map((source, index) => {
    const repo = isRecord(data) ? data[`s${index}`] : undefined;
    const latest = firstOid(repo, "head");
    if (!latest) {
      throw new Error(`${source.repository} has no commit touching ${source.ref}:${source.path}`);
    }
    const reviewed = firstOid(repo, "reviewed");
    if (!reviewed) {
      throw new Error(
        `${source.repository} has no reviewed commit ${source.reviewedCommit} touching ${source.path}`,
      );
    }
    return { latest, reviewed };
  });
}

/** A source changed when the watched path has a commit newer than the one the maintainer reviewed. */
export function isChanged(state: SourceState): boolean {
  return state.latest !== state.reviewed;
}

export function changedSources(sources: WatchSource[], states: SourceState[]): WatchSource[] {
  return sources.filter((_, index) => {
    const state = states[index];
    if (state === undefined) {
      throw new Error(`No upstream state for source ${index}`);
    }
    return isChanged(state);
  });
}

export function compareUrl(source: WatchSource, latest: string): string {
  return `https://github.com/${source.repository}/compare/${source.reviewedCommit}...${latest}`;
}

export function driftMarker(source: WatchSource, state: SourceState): string {
  const digest = new Bun.CryptoHasher("sha256")
    .update(JSON.stringify({ name: source.name, latest: state.latest }))
    .digest("hex");
  return `<!-- upstream-watch-current:${digest} -->`;
}

export function issueBody(
  config: WatchConfig,
  source: WatchSource,
  state: SourceState,
  marker: string,
): string {
  return [
    `@${config.assignee} \`${source.repository}\` changed \`${source.path}\` on \`${source.ref}\`. \`${source.target}\` was vendored from it and is not synced.`,
    "",
    "| Field | Value |",
    "| --- | --- |",
    `| Source | \`${source.name}\` |`,
    `| Repository | [${source.repository}](https://github.com/${source.repository}) |`,
    `| Watched path | \`${source.ref}:${source.path}\` |`,
    `| Pinned (reviewed) commit | [${source.reviewedCommit.slice(0, 12)}](https://github.com/${source.repository}/commit/${source.reviewedCommit}) |`,
    `| Latest commit touching the path | [${state.latest.slice(0, 12)}](https://github.com/${source.repository}/commit/${state.latest}) |`,
    `| Vendored target | \`${source.target}\` |`,
    "",
    `Compare: ${compareUrl(source, state.latest)}`,
    "",
    "To resolve:",
    "",
    "1. Review the upstream diff above, limited to the watched path.",
    `2. Port or adapt what is useful into \`${source.target}\`, preserving each skill's voice and structure.`,
    "3. Run the repository gates (`bun test scripts`, `bun scripts/sync.ts --check`).",
    `4. Update \`reviewedCommit\` for \`${source.name}\` in \`upstream-watch.json\` to \`${state.latest}\` (or the newest upstream commit you reviewed).`,
    "5. Close this issue. The next run also closes it once the pin is current.",
    "",
    OWNERSHIP_MARKER,
    marker,
  ].join("\n");
}

/** Only issues this automation created may be selected or written: authored by the workflow bot and carrying the ownership marker. */
export function isOwned(issue: Issue): boolean {
  return issue.user?.login === NOTIFICATION_AUTHOR && (issue.body ?? "").includes(OWNERSHIP_MARKER);
}

/**
 * Refuse to notify from a repository other than the configured one, or from a GitHub Actions run on any ref but main.
 * Runs outside GitHub Actions skip the ref check so maintainers can notify manually.
 */
export function assertNotifyContext(repository: string, env: NotifyEnv = process.env): void {
  if (env.GITHUB_REPOSITORY !== repository) {
    throw new Error(
      `Refusing to notify ${repository} from GITHUB_REPOSITORY=${env.GITHUB_REPOSITORY ?? "<unset>"}`,
    );
  }
  if (env.GITHUB_ACTIONS === "true" && env.GITHUB_REF !== NOTIFY_REF) {
    throw new Error(
      `Refusing to notify ${repository} from GITHUB_REF=${env.GITHUB_REF ?? "<unset>"}; only ${NOTIFY_REF} may write issues`,
    );
  }
}

export type NotifyAction = "create" | "refresh" | "close" | "resolve" | "none";

/**
 * Issue body state is explicit and deterministic:
 * - a body containing the exact current drift marker reports that drift;
 * - a body containing RESOLVED_MARKER reports nothing. It is written whenever the pin matches again, whether the
 *   issue was open (auto-closed) or closed by a maintainer (dismissed), because a recurrence is then new drift.
 * While the same drift persists, a maintainer-closed issue stays dismissed. Any drift whose marker the body lacks,
 * including a recurrence equal to an older report, refreshes and reopens the issue.
 */
export function notifyAction(
  existing: Issue | undefined,
  changed: boolean,
  marker: string,
): NotifyAction {
  if (!changed) {
    if (existing?.state === "open") {
      return "close";
    }
    return existing && DRIFT_MARKER.test(existing.body ?? "") ? "resolve" : "none";
  }
  if (!existing) {
    return "create";
  }
  return existing.body?.includes(marker) ? "none" : "refresh";
}

/** Replace the drift marker with the resolved marker so a recurrence of the same drift is not mistaken for a dismissal. */
export function resolvedBody(body: string | null): string {
  const kept = (body ?? "").replaceAll(DRIFT_MARKER_LINE, "").trimEnd();
  return kept.includes(RESOLVED_MARKER) ? kept : `${kept}${kept ? "\n\n" : ""}${RESOLVED_MARKER}`;
}

/**
 * Scan every issue page (never just the newest) for same-title issues this automation owns; pull requests and foreign
 * issues (another author, or no ownership marker) are excluded. Matches are oldest first.
 */
export async function scanIssues(
  repository: string,
  title: string,
  request: Request,
): Promise<{ canonical: Issue | undefined; matches: Issue[] }> {
  const matches: Issue[] = [];
  let canonical: Issue | undefined;
  for (let page = 1; ; page++) {
    const issues = await request(
      `/repos/${repository}/issues?state=all&sort=created&direction=asc&per_page=${ISSUES_PER_PAGE}&page=${page}`,
      { method: "GET" },
      [200],
    );
    if (!Array.isArray(issues) || !issues.every(isIssue)) {
      throw new Error(`GitHub REST returned an unexpected issue list for ${repository}`);
    }
    for (const issue of issues) {
      if (issue.pull_request || issue.title !== title || !isOwned(issue)) {
        continue;
      }
      matches.push(issue);
      // Prefer an open issue, then the oldest.
      if (!canonical || (issue.state === "open" && canonical.state !== "open")) {
        canonical = issue;
      }
    }
    if (issues.length < ISSUES_PER_PAGE) {
      return { canonical, matches };
    }
  }
}

/** Create, refresh, or close the single issue for one source. Writes nothing when the issue already reflects the state. */
export async function notifySource(
  config: WatchConfig,
  source: WatchSource,
  state: SourceState,
  request: Request = rest,
): Promise<void> {
  const { repository, assignee } = config;
  const { canonical: existing, matches } = await scanIssues(repository, source.issueTitle, request);
  const changed = isChanged(state);
  const marker = driftMarker(source, state);
  if (!changed) {
    // Resolve every duplicate, not just the canonical one: a stale drift marker left on any duplicate could later be
    // selected as canonical and make a recurrence of that drift look deliberately dismissed.
    for (const issue of matches) {
      const action = notifyAction(issue, false, marker);
      if (action === "none") {
        continue;
      }
      // A dismissed (already closed) issue only has its drift marker cleared; its closed state is left alone.
      const patch =
        action === "close"
          ? { state: "closed", body: resolvedBody(issue.body) }
          : { body: resolvedBody(issue.body) };
      await request(
        `/repos/${repository}/issues/${issue.number}`,
        { method: "PATCH", body: JSON.stringify(patch) },
        [200],
      );
      process.stdout.write(
        `resolved ${source.name} issue #${issue.number}${action === "close" ? " (closed)" : ""}\n`,
      );
    }
    return;
  }
  const action = notifyAction(existing, changed, marker);
  if (action === "create") {
    const body = issueBody(config, source, state, marker);
    const created = await request(
      `/repos/${repository}/issues`,
      {
        method: "POST",
        body: JSON.stringify({ title: source.issueTitle, body, assignees: [assignee] }),
      },
      [201],
    );
    const number = isRecord(created) ? created.number : undefined;
    if (typeof number !== "number") {
      throw new Error(`GitHub REST returned no issue number for ${repository}`);
    }
    process.stdout.write(`opened ${source.name} issue #${number}\n`);
    return;
  }
  // notifyAction returns "create" whenever there is no existing issue.
  if (!existing) {
    throw new Error(`No existing ${source.name} issue to ${action}`);
  }
  if (action === "none") {
    process.stdout.write(
      `${source.name} change already ${existing.state === "open" ? "reported" : "dismissed"} in issue #${existing.number}\n`,
    );
    return;
  }
  const body = issueBody(config, source, state, marker);
  await request(
    `/repos/${repository}/issues/${existing.number}`,
    { method: "PATCH", body: JSON.stringify({ body, state: "open", assignees: [assignee] }) },
    [200],
  );
  await request(
    `/repos/${repository}/issues/${existing.number}/comments`,
    {
      method: "POST",
      body: JSON.stringify({
        body: `@${assignee} \`${source.repository}\` changed again; the body above is current.`,
      }),
    },
    [201],
  );
  process.stdout.write(`updated ${source.name} issue #${existing.number}\n`);
}

/** Notify for every source. Refuses before any request when run from another repository or a non-main Actions ref. */
export async function notify(
  config: WatchConfig,
  states: SourceState[],
  request: Request = rest,
  env: NotifyEnv = process.env,
): Promise<void> {
  assertNotifyContext(config.repository, env);
  for (const [index, source] of config.sources.entries()) {
    const state = states[index];
    if (state === undefined) {
      throw new Error(`No upstream state for source ${source.name}`);
    }
    await notifySource(config, source, state, request);
  }
}

if (import.meta.main) {
  const config = parseConfig(await Bun.file(CONFIG_PATH).json());
  const notifyMode = process.argv.includes("--notify");
  // Fail on a wrong repository or ref before spending any API calls.
  if (notifyMode) {
    assertNotifyContext(config.repository);
  }
  const states = await fetchStates(config.sources);
  const changed = changedSources(config.sources, states);
  if (notifyMode) {
    await notify(config, states);
  }
  if (changed.length === 0) {
    process.stdout.write(
      `Upstream watch: ${config.sources.length} source(s) match their reviewed commits\n`,
    );
  } else {
    for (const source of changed) {
      const state = states[config.sources.indexOf(source)];
      if (state === undefined) {
        throw new Error(`No upstream state for source ${source.name}`);
      }
      process.stderr.write(
        `${source.name}: ${source.repository} ${source.path} ${source.reviewedCommit} -> ${state.latest} (${compareUrl(source, state.latest)})\n`,
      );
    }
    if (!notifyMode) {
      process.exitCode = 1;
    }
  }
}
