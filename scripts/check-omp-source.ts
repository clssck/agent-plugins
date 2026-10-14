#!/usr/bin/env bun
// Watches the OMP sources clssck-development was adapted from. It never syncs files:
// a change opens (or refreshes) one assigned issue so a maintainer can review and adopt it by hand.

import * as path from "node:path";
import { githubGraphql, githubRepositoryField } from "./github";

interface NotificationConfig {
	repository: string;
	assignee: string;
	issueTitle: string;
}

interface SourceLock {
	repository: string;
	ref: string;
	reviewedCommit: string;
	trees: Record<string, string>;
	notification: NotificationConfig;
}

interface Issue {
	number: number;
	title: string;
	body: string | null;
	state: "open" | "closed";
	pull_request?: unknown;
}

const LOCK_PATH = path.resolve(import.meta.dir, "..", "omp-source-lock.json");

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

async function notify(lock: SourceLock, head: string, current: Record<string, string | null>, changed: boolean): Promise<void> {
	const { repository, assignee, issueTitle } = lock.notification;
	if (process.env.GITHUB_REPOSITORY !== repository) {
		throw new Error(`Refusing to notify ${repository} from GITHUB_REPOSITORY=${process.env.GITHUB_REPOSITORY ?? "<unset>"}`);
	}
	const issues = await rest<Issue[]>(`/repos/${repository}/issues?state=all&sort=updated&direction=desc&per_page=100`, { method: "GET" }, [200]);
	const existing = issues.find(issue => !issue.pull_request && issue.title === issueTitle);
	if (!changed) {
		if (existing?.state === "open") {
			await rest(`/repos/${repository}/issues/${existing.number}`, { method: "PATCH", body: JSON.stringify({ state: "closed" }) }, [200]);
			console.log(`closed resolved baseline issue #${existing.number}`);
		}
		return;
	}

	const marker = `<!-- omp-source-current:${new Bun.CryptoHasher("sha256").update(JSON.stringify(current)).digest("hex")} -->`;
	const body = issueBody(lock, head, current, marker);
	if (!existing) {
		const created = await rest<Issue>(
			`/repos/${repository}/issues`,
			{ method: "POST", body: JSON.stringify({ title: issueTitle, body, assignees: [assignee] }) },
			[201],
		);
		console.log(`opened baseline issue #${created.number}`);
		return;
	}
	if (existing.body?.includes(marker)) {
		console.log(`baseline change already ${existing.state === "open" ? "reported" : "dismissed"} in issue #${existing.number}`);
		return;
	}
	await rest(
		`/repos/${repository}/issues/${existing.number}`,
		{ method: "PATCH", body: JSON.stringify({ body, state: "open", assignees: [assignee] }) },
		[200],
	);
	await rest(
		`/repos/${repository}/issues/${existing.number}/comments`,
		{ method: "POST", body: JSON.stringify({ body: `@${assignee} OMP changed again; the table above is current.` }) },
		[201],
	);
	console.log(`updated baseline issue #${existing.number}`);
}

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
