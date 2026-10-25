#!/usr/bin/env bun
// Watches the OMP command sources `clssck` was adapted from. It never syncs files:
// a change opens (or refreshes) one assigned issue so a maintainer can review and adopt it by hand.

import * as path from "node:path";
import { githubGraphql, githubRepositoryField } from "./github";

export interface NotificationConfig {
  repository: string;
  assignee: string;
  issueTitle: string;
}

export interface SourceLock {
  repository: string;
  ref: string;
  reviewedCommit: string;
  trees: Record<string, string>;
  notification: NotificationConfig;
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

const LOCK_PATH = path.resolve(import.meta.dir, "..", "omp-source-lock.json");

type Request = (endpoint: string, init: RequestInit, allowed: number[]) => Promise<unknown>;

const ISSUES_PER_PAGE = 100;
const RESOLVED_MARKER = "<!-- omp-source-resolved -->";
const DRIFT_MARKER_LINE = /^<!-- omp-source-current:[0-9a-f]+ -->[ \t]*$/gm;
const DRIFT_MARKER = /<!-- omp-source-current:[0-9a-f]+ -->/;
/** Login GitHub records as the author of issues created with the workflow's `github.token`. */
export const NOTIFICATION_AUTHOR = "github-actions[bot]";
/** Stable hidden marker in every body this automation writes; unlike the drift marker it never changes. */
export const OWNERSHIP_MARKER = "<!-- agent-plugins:omp-source-notification -->";
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

function isIssue(value: unknown): value is Issue {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const userOk =
    "user" in value &&
    (value.user === null ||
      (typeof value.user === "object" &&
        value.user !== null &&
        "login" in value.user &&
        typeof value.user.login === "string"));
  return (
    "number" in value &&
    typeof value.number === "number" &&
    "title" in value &&
    typeof value.title === "string" &&
    "body" in value &&
    (value.body === null || typeof value.body === "string") &&
    "state" in value &&
    (value.state === "open" || value.state === "closed") &&
    userOk
  );
}

function isSourceLock(value: unknown): value is SourceLock {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  return (
    "repository" in value &&
    typeof value.repository === "string" &&
    "ref" in value &&
    typeof value.ref === "string" &&
    "reviewedCommit" in value &&
    typeof value.reviewedCommit === "string" &&
    "trees" in value &&
    typeof value.trees === "object" &&
    value.trees !== null &&
    Object.values(value.trees).every((tree) => typeof tree === "string") &&
    "notification" in value &&
    typeof value.notification === "object" &&
    value.notification !== null &&
    "repository" in value.notification &&
    typeof value.notification.repository === "string" &&
    "assignee" in value.notification &&
    typeof value.notification.assignee === "string" &&
    "issueTitle" in value.notification &&
    typeof value.notification.issueTitle === "string"
  );
}

async function currentTrees(
  lock: SourceLock,
): Promise<{ head: string; trees: Record<string, string | null> }> {
  const paths = Object.keys(lock.trees).toSorted();
  const fields = paths.map(
    (sourcePath, index) =>
      `p${index}: object(expression: ${JSON.stringify(`${lock.ref}:${sourcePath}`)}) { oid }`,
  );
  const data = await githubGraphql<{ repository: Record<string, { oid: string } | null> | null }>(
    `query { ${githubRepositoryField(lock.repository)} { head: object(expression: ${JSON.stringify(lock.ref)}) { oid } ${fields.join(" ")} } }`,
  );
  const head = data.repository?.head?.oid;
  if (!head) {
    throw new Error(`${lock.repository} has no ref ${lock.ref}`);
  }
  const trees: Record<string, string | null> = {};
  for (const [index, sourcePath] of paths.entries()) {
    trees[sourcePath] = data.repository?.[`p${index}`]?.oid ?? null;
  }
  return { head, trees };
}

function treeUrl(repository: string, commit: string, sourcePath: string): string {
  return `https://github.com/${repository}/tree/${commit}/${sourcePath.split("/").map(encodeURIComponent).join("/")}`;
}

function issueBody(
  lock: SourceLock,
  head: string,
  current: Record<string, string | null>,
  marker: string,
): string {
  const rows = Object.keys(lock.trees)
    .toSorted()
    .map((sourcePath) => {
      const reviewedTree = lock.trees[sourcePath];
      if (reviewedTree === undefined) {
        throw new Error(`OMP source lock has no tree for ${sourcePath}`);
      }
      const reviewed = `[${reviewedTree.slice(0, 12)}](${treeUrl(lock.repository, lock.reviewedCommit, sourcePath)})`;
      const actual = current[sourcePath];
      const latest = actual
        ? `[${actual.slice(0, 12)}](${treeUrl(lock.repository, head, sourcePath)})`
        : "missing";
      return `| \`${sourcePath}\` | ${reviewed} | ${latest} |`;
    });
  return [
    `@${lock.notification.assignee} OMP changed command sources that \`clssck\` was adapted from.`,
    "",
    "| Source path | Reviewed tree | Current tree |",
    "| --- | --- | --- |",
    ...rows,
    "",
    `Compare: https://github.com/${lock.repository}/compare/${lock.reviewedCommit}...${head}`,
    "",
    "`clssck` is first-party and is not synced. Review the diff, adapt anything useful by hand, then update `omp-source-lock.json` to the reviewed commit and tree.",
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
 * - a body containing RESOLVED_MARKER reports nothing. It is written whenever the baseline matches again, whether the
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

export function driftMarker(current: Record<string, string | null>): string {
  const sorted = Object.fromEntries(
    Object.entries(current).toSorted(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
  );
  return `<!-- omp-source-current:${new Bun.CryptoHasher("sha256").update(JSON.stringify(sorted)).digest("hex")} -->`;
}

interface NotificationIssues {
  /** The issue drift is reported in: an open issue if any, otherwise the oldest. */
  canonical: Issue | undefined;
  /** Every same-title non-PR issue this automation owns, oldest first; duplicates may carry stale drift markers. */
  matches: Issue[];
}

/**
 * Scan every issue page (never just the newest) for same-title issues this automation owns; pull requests and foreign
 * issues (another author, or no ownership marker) are excluded.
 */
async function scanNotificationIssues(
  repository: string,
  title: string,
  request: Request,
): Promise<NotificationIssues> {
  const matches: Issue[] = [];
  let canonical: Issue | undefined;
  for (let page = 1; ; page++) {
    const issues = await request(
      `/repos/${repository}/issues?state=all&sort=created&direction=asc&per_page=${ISSUES_PER_PAGE}&page=${page}`,
      { method: "GET" },
      [200],
    );
    if (!Array.isArray(issues) || !issues.every(isIssue)) {
      throw new Error(`GitHub returned an unexpected issues page for ${repository}`);
    }
    for (const issue of issues) {
      if (issue.pull_request || issue.title !== title || !isOwned(issue)) {
        continue;
      }
      matches.push(issue);
      if (!canonical || (issue.state === "open" && canonical.state !== "open")) {
        canonical = issue;
      }
    }
    if (issues.length < ISSUES_PER_PAGE) {
      return { canonical, matches };
    }
  }
}

/** Scan every issue page (never just the newest) for the owned notification issue; pull requests and foreign issues are excluded. Prefers an open issue, then the oldest. */
export async function findNotificationIssue(
  repository: string,
  title: string,
  request: Request = rest,
): Promise<Issue | undefined> {
  return (await scanNotificationIssues(repository, title, request)).canonical;
}

export async function notify(
  lock: SourceLock,
  head: string,
  current: Record<string, string | null>,
  changed: boolean,
  request: Request = rest,
  env: NotifyEnv = process.env,
): Promise<void> {
  const { repository, assignee, issueTitle } = lock.notification;
  assertNotifyContext(repository, env);
  const { canonical: existing, matches } = await scanNotificationIssues(
    repository,
    issueTitle,
    request,
  );
  const marker = driftMarker(current);
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
        `resolved baseline issue #${issue.number}${action === "close" ? " (closed)" : ""}\n`,
      );
    }
    return;
  }
  const action = notifyAction(existing, changed, marker);
  // notifyAction returns "create" exactly when there is no existing issue.
  if (action === "create" || existing === undefined) {
    const created = await request(
      `/repos/${repository}/issues`,
      {
        method: "POST",
        body: JSON.stringify({
          title: issueTitle,
          body: issueBody(lock, head, current, marker),
          assignees: [assignee],
        }),
      },
      [201],
    );
    if (
      typeof created !== "object" ||
      created === null ||
      !("number" in created) ||
      typeof created.number !== "number"
    ) {
      throw new Error(`GitHub returned no issue number for the issue created in ${repository}`);
    }
    process.stdout.write(`opened baseline issue #${created.number}\n`);
    return;
  }
  if (action === "none") {
    process.stdout.write(
      `baseline change already ${existing.state === "open" ? "reported" : "dismissed"} in issue #${existing.number}\n`,
    );
    return;
  }

  const body = issueBody(lock, head, current, marker);
  await request(
    `/repos/${repository}/issues/${existing.number}`,
    { method: "PATCH", body: JSON.stringify({ body, state: "open", assignees: [assignee] }) },
    [200],
  );
  await request(
    `/repos/${repository}/issues/${existing.number}/comments`,
    {
      method: "POST",
      body: JSON.stringify({ body: `@${assignee} OMP changed again; the table above is current.` }),
    },
    [201],
  );
  process.stdout.write(`updated baseline issue #${existing.number}\n`);
}

if (import.meta.main) {
  const lock: unknown = await Bun.file(LOCK_PATH).json();
  if (
    !isSourceLock(lock) ||
    !lock.repository ||
    !lock.ref ||
    !lock.reviewedCommit ||
    Object.keys(lock.trees).length === 0
  ) {
    throw new Error(`Invalid OMP source lock: ${LOCK_PATH}`);
  }
  // Refuse a wrong repository or ref before spending any API calls.
  if (process.argv.includes("--notify")) {
    assertNotifyContext(lock.notification.repository);
  }
  const current = await currentTrees(lock);
  const changed = Object.keys(lock.trees)
    .toSorted()
    .filter((sourcePath) => lock.trees[sourcePath] !== current.trees[sourcePath]);
  if (process.argv.includes("--notify")) {
    await notify(lock, current.head, current.trees, changed.length > 0);
  }
  if (changed.length === 0) {
    process.stdout.write(`OMP baseline matches ${lock.repository}@${current.head.slice(0, 12)}\n`);
  } else {
    for (const sourcePath of changed) {
      process.stderr.write(
        `${sourcePath}: ${lock.trees[sourcePath]} -> ${current.trees[sourcePath] ?? "missing"}\n`,
      );
    }
    if (!process.argv.includes("--notify")) {
      process.exitCode = 1;
    }
  }
}
