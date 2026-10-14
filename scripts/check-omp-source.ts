#!/usr/bin/env bun
// Watches the OMP sources clssck-development was adapted from. It never syncs files:
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
	pull_request?: unknown;
}

const LOCK_PATH = path.resolve(import.meta.dir, "..", "omp-source-lock.json");

type Request = <T>(endpoint: string, init: RequestInit, allowed: number[]) => Promise<T>;

const ISSUES_PER_PAGE = 100;
const RESOLVED_MARKER = "<!-- omp-source-resolved -->";
const DRIFT_MARKER_LINE = /^<!-- omp-source-current:[0-9a-f]+ -->[ \t]*$/gm;
const DRIFT_MARKER = /<!-- omp-source-current:[0-9a-f]+ -->/;

async function rest<T>(endpoint: string, init: RequestInit, allowed: number[]): Promise<T> {
	const token = process.env.GITHUB_TOKEN;
	if (!token) throw new Error("GITHUB_TOKEN is required");
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
	if (!allowed.includes(response.status)) throw new Error(`GitHub REST ${response.status} for ${endpoint}: ${await response.text()}`);
	return (await response.json()) as T;
}

async function currentTrees(lock: SourceLock): Promise<{ head: string; trees: Record<string, string | null> }> {
	const paths = Object.keys(lock.trees).sort();
	const fields = paths.map((sourcePath, index) => `p${index}: object(expression: ${JSON.stringify(`${lock.ref}:${sourcePath}`)}) { oid }`);
	const data = await githubGraphql<{ repository: Record<string, { oid: string } | null> | null }>(
		`query { ${githubRepositoryField(lock.repository)} { head: object(expression: ${JSON.stringify(lock.ref)}) { oid } ${fields.join(" ")} } }`,
	);
	const head = data.repository?.head?.oid;
	if (!head) throw new Error(`${lock.repository} has no ref ${lock.ref}`);
	const trees: Record<string, string | null> = {};
	for (const [index, sourcePath] of paths.entries()) trees[sourcePath] = data.repository?.[`p${index}`]?.oid ?? null;
	return { head, trees };
}

function treeUrl(repository: string, commit: string, sourcePath: string): string {
	return `https://github.com/${repository}/tree/${commit}/${sourcePath.split("/").map(encodeURIComponent).join("/")}`;
}

function issueBody(lock: SourceLock, head: string, current: Record<string, string | null>, marker: string): string {
	const rows = Object.keys(lock.trees).sort().map(sourcePath => {
		const reviewed = `[${lock.trees[sourcePath].slice(0, 12)}](${treeUrl(lock.repository, lock.reviewedCommit, sourcePath)})`;
		const actual = current[sourcePath];
		const latest = actual ? `[${actual.slice(0, 12)}](${treeUrl(lock.repository, head, sourcePath)})` : "missing";
		return `| \`${sourcePath}\` | ${reviewed} | ${latest} |`;
	});
	return [
		`@${lock.notification.assignee} OMP changed sources that \`clssck-development\` was adapted from.`,
		"",
		"| Source path | Reviewed tree | Current tree |",
		"| --- | --- | --- |",
		...rows,
		"",
		`Compare: https://github.com/${lock.repository}/compare/${lock.reviewedCommit}...${head}`,
		"",
		"`clssck-development` is first-party and is not synced. Review the diff, adapt anything useful by hand, then update `omp-source-lock.json` to the reviewed commit and trees.",
		"",
		marker,
	].join("\n");
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
export function notifyAction(existing: Issue | undefined, changed: boolean, marker: string): NotifyAction {
	if (!changed) {
		if (existing?.state === "open") return "close";
		return existing && DRIFT_MARKER.test(existing.body ?? "") ? "resolve" : "none";
	}
	if (!existing) return "create";
	return existing.body?.includes(marker) ? "none" : "refresh";
}

/** Replace the drift marker with the resolved marker so a recurrence of the same drift is not mistaken for a dismissal. */
export function resolvedBody(body: string | null): string {
	const kept = (body ?? "").replace(DRIFT_MARKER_LINE, "").trimEnd();
	return kept.includes(RESOLVED_MARKER) ? kept : `${kept}${kept ? "\n\n" : ""}${RESOLVED_MARKER}`;
}

export function driftMarker(current: Record<string, string | null>): string {
	const sorted = Object.fromEntries(Object.entries(current).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
	return `<!-- omp-source-current:${new Bun.CryptoHasher("sha256").update(JSON.stringify(sorted)).digest("hex")} -->`;
}

interface NotificationIssues {
	/** The issue drift is reported in: an open issue if any, otherwise the oldest. */
	canonical: Issue | undefined;
	/** Every same-title non-PR issue, oldest first; duplicates may carry stale drift markers. */
	matches: Issue[];
}

/** Scan every issue page (never just the newest) for same-title issues; pull requests are excluded. */
async function scanNotificationIssues(repository: string, title: string, request: Request): Promise<NotificationIssues> {
	const matches: Issue[] = [];
	let canonical: Issue | undefined;
	for (let page = 1; ; page++) {
		const issues = await request<Issue[]>(
			`/repos/${repository}/issues?state=all&sort=created&direction=asc&per_page=${ISSUES_PER_PAGE}&page=${page}`,
			{ method: "GET" },
			[200],
		);
		for (const issue of issues) {
			if (issue.pull_request || issue.title !== title) continue;
			matches.push(issue);
			if (!canonical || (issue.state === "open" && canonical.state !== "open")) canonical = issue;
		}
		if (issues.length < ISSUES_PER_PAGE) return { canonical, matches };
	}
}

/** Scan every issue page (never just the newest) for the notification issue; pull requests are excluded. Prefers an open issue, then the oldest. */
export async function findNotificationIssue(repository: string, title: string, request: Request = rest): Promise<Issue | undefined> {
	return (await scanNotificationIssues(repository, title, request)).canonical;
}

export async function notify(
	lock: SourceLock,
	head: string,
	current: Record<string, string | null>,
	changed: boolean,
	request: Request = rest,
	githubRepository: string | undefined = process.env.GITHUB_REPOSITORY,
): Promise<void> {
	const { repository, assignee, issueTitle } = lock.notification;
	if (githubRepository !== repository) {
		throw new Error(`Refusing to notify ${repository} from GITHUB_REPOSITORY=${githubRepository ?? "<unset>"}`);
	}
	const { canonical: existing, matches } = await scanNotificationIssues(repository, issueTitle, request);
	const marker = driftMarker(current);
	if (!changed) {
		// Resolve every duplicate, not just the canonical one: a stale drift marker left on any duplicate could later be
		// selected as canonical and make a recurrence of that drift look deliberately dismissed.
		for (const issue of matches) {
			const action = notifyAction(issue, false, marker);
			if (action === "none") continue;
			// A dismissed (already closed) issue only has its drift marker cleared; its closed state is left alone.
			const patch = action === "close" ? { state: "closed", body: resolvedBody(issue.body) } : { body: resolvedBody(issue.body) };
			await request(`/repos/${repository}/issues/${issue.number}`, { method: "PATCH", body: JSON.stringify(patch) }, [200]);
			console.log(`resolved baseline issue #${issue.number}${action === "close" ? " (closed)" : ""}`);
		}
		return;
	}
	const action = notifyAction(existing, changed, marker);
	if (action === "none") {
		console.log(`baseline change already ${existing!.state === "open" ? "reported" : "dismissed"} in issue #${existing!.number}`);
		return;
	}

	const body = issueBody(lock, head, current, marker);
	if (action === "create") {
		const created = await request<Issue>(
			`/repos/${repository}/issues`,
			{ method: "POST", body: JSON.stringify({ title: issueTitle, body, assignees: [assignee] }) },
			[201],
		);
		console.log(`opened baseline issue #${created.number}`);
		return;
	}
	await request(
		`/repos/${repository}/issues/${existing!.number}`,
		{ method: "PATCH", body: JSON.stringify({ body, state: "open", assignees: [assignee] }) },
		[200],
	);
	await request(
		`/repos/${repository}/issues/${existing!.number}/comments`,
		{ method: "POST", body: JSON.stringify({ body: `@${assignee} OMP changed again; the table above is current.` }) },
		[201],
	);
	console.log(`updated baseline issue #${existing!.number}`);
}

if (import.meta.main) {
	const lock = (await Bun.file(LOCK_PATH).json()) as SourceLock;
	if (!lock.repository || !lock.ref || !lock.reviewedCommit || Object.keys(lock.trees ?? {}).length === 0) {
		throw new Error(`Invalid OMP source lock: ${LOCK_PATH}`);
	}
	const current = await currentTrees(lock);
	const changed = Object.keys(lock.trees).sort().filter(sourcePath => lock.trees[sourcePath] !== current.trees[sourcePath]);
	if (process.argv.includes("--notify")) await notify(lock, current.head, current.trees, changed.length > 0);
	if (changed.length === 0) {
		console.log(`OMP baseline matches ${lock.repository}@${current.head.slice(0, 12)}`);
	} else {
		for (const sourcePath of changed) console.error(`${sourcePath}: ${lock.trees[sourcePath]} -> ${current.trees[sourcePath] ?? "missing"}`);
		if (!process.argv.includes("--notify")) process.exitCode = 1;
	}
}
