#!/usr/bin/env bun

import * as path from "node:path";
import { githubGraphql as graphql, githubRepositoryField } from "./github";

interface NotificationConfig {
	repository: string;
	assignee: string;
	issueTitle: string;
}

interface SourceLock {
	repository: string;
	ref: string;
	snapshotCommit: string;
	trees: Record<string, string>;
	notification: NotificationConfig;
}

interface GitObject {
	oid: string;
}

interface Issue {
	number: number;
	title: string;
	body: string | null;
	state: "open" | "closed";
	pull_request?: unknown;
}

const ROOT = path.resolve(import.meta.dir, "..");
const LOCK_PATH = process.env.OMP_SOURCE_LOCK ?? path.join(ROOT, "omp-source-lock.json");
const NOTIFY = process.argv.includes("--notify");

function requireToken(): string {
	const token = process.env.GITHUB_TOKEN;
	if (!token) throw new Error("GITHUB_TOKEN is required");
	return token;
}

async function rest<T>(endpoint: string, init: RequestInit, allowed: number[]): Promise<T | undefined> {
	const response = await fetch("https://api.github.com" + endpoint, {
		...init,
		headers: {
			Accept: "application/vnd.github+json",
			Authorization: "Bearer " + requireToken(),
			"Content-Type": "application/json",
			"User-Agent": "clssck-agent-plugins",
			"X-GitHub-Api-Version": "2022-11-28",
		},
	});
	if (!allowed.includes(response.status)) {
		throw new Error("GitHub REST " + response.status + " for " + endpoint + ": " + (await response.text()));
	}
	if (response.status === 204) return undefined;
	return (await response.json()) as T;
}

async function currentTrees(lock: SourceLock): Promise<{ head: string; trees: Record<string, string | null> }> {
	const repository = githubRepositoryField(lock.repository);
	const paths = Object.keys(lock.trees).sort();
	const fields = paths.map((sourcePath, index) =>
		"p" + index + ": object(expression: " + JSON.stringify(lock.ref + ":" + sourcePath) + ") { oid }",
	);
	const query = "query { " + repository + " { " +
		"head: object(expression: " + JSON.stringify(lock.ref) + ") { oid } " + fields.join(" ") + " } }";
	const data = await graphql<{ repository: (Record<string, GitObject | null> & { head: GitObject | null }) | null }>(query);
	if (!data.repository?.head?.oid) throw new Error(lock.repository + " has no ref " + lock.ref);
	const trees: Record<string, string | null> = {};
	paths.forEach((sourcePath, index) => {
		trees[sourcePath] = data.repository?.["p" + index]?.oid ?? null;
	});
	return { head: data.repository.head.oid, trees };
}

function issueMarker(trees: Record<string, string | null>): string {
	const fingerprint = new Bun.CryptoHasher("sha256").update(JSON.stringify(trees)).digest("hex");
	return "<!-- omp-source-current:" + fingerprint + " -->";
}

function treeUrl(repository: string, commit: string, sourcePath: string): string {
	const encodedPath = sourcePath.split("/").map(encodeURIComponent).join("/");
	return "https://github.com/" + repository + "/tree/" + commit + "/" + encodedPath;
}

function issueBody(lock: SourceLock, head: string, current: Record<string, string | null>): string {
	const rows = Object.keys(lock.trees).sort().map(sourcePath => {
		const expected = lock.trees[sourcePath];
		const actual = current[sourcePath];
		const expectedCell = "[" + expected.slice(0, 12) + "](" + treeUrl(lock.repository, lock.snapshotCommit, sourcePath) + ")";
		const actualCell = actual
			? "[" + actual.slice(0, 12) + "](" + treeUrl(lock.repository, head, sourcePath) + ")"
			: "missing";
		return "| " + sourcePath + " | " + expectedCell + " | " + actualCell + " |";
	});
	return [
		"@" + lock.notification.assignee + " the reviewed OMP development snapshot no longer matches upstream.",
		"",
		"| Source path | Snapshot tree | Current tree |",
		"| --- | --- | --- |",
		...rows,
		"",
		"Source comparison: https://github.com/" + lock.repository + "/compare/" + lock.snapshotCommit + "..." + head,
		"",
		"Review the upstream diff, update packs/omp-development, then update omp-source-lock.json. The snapshot is intentionally not auto-synced because it carries packaging fixes.",
		"",
		issueMarker(current),
	].join("\n");
}

async function findIssue(config: NotificationConfig): Promise<Issue | undefined> {
	const issues = await rest<Issue[]>(
		"/repos/" + config.repository + "/issues?state=all&sort=updated&direction=desc&per_page=100",
		{ method: "GET" },
		[200],
	);
	return issues?.find(issue => !issue.pull_request && issue.title === config.issueTitle);
}

async function notify(lock: SourceLock, head: string, current: Record<string, string | null>, drifted: boolean): Promise<void> {
	const runtimeRepository = process.env.GITHUB_REPOSITORY;
	if (runtimeRepository !== lock.notification.repository) {
		throw new Error(
			"Refusing to notify " + lock.notification.repository + " from GITHUB_REPOSITORY=" + (runtimeRepository ?? "<unset>"),
		);
	}
	const existing = await findIssue(lock.notification);
	if (!drifted) {
		if (existing?.state === "open") {
			await rest(
				"/repos/" + lock.notification.repository + "/issues/" + existing.number,
				{ method: "PATCH", body: JSON.stringify({ state: "closed" }) },
				[200],
			);
			console.log("closed resolved drift issue #" + existing.number);
		}
		return;
	}

	const body = issueBody(lock, head, current);
	const marker = issueMarker(current);
	if (!existing) {
		const created = await rest<Issue>(
			"/repos/" + lock.notification.repository + "/issues",
			{
				method: "POST",
				body: JSON.stringify({
					title: lock.notification.issueTitle,
					body,
					assignees: [lock.notification.assignee],
				}),
			},
			[201],
		);
		console.log("opened drift issue #" + created?.number);
		return;
	}
	if (existing.body?.includes(marker)) {
		console.log(
			existing.state === "open"
				? "drift already reported in issue #" + existing.number
				: "drift dismissed in closed issue #" + existing.number,
		);
		return;
	}
	await rest(
		"/repos/" + lock.notification.repository + "/issues/" + existing.number,
		{
			method: "PATCH",
			body: JSON.stringify({ body, state: "open", assignees: [lock.notification.assignee] }),
		},
		[200],
	);
	await rest(
		"/repos/" + lock.notification.repository + "/issues/" + existing.number + "/comments",
		{
			method: "POST",
			body: JSON.stringify({ body: "@" + lock.notification.assignee + " upstream changed again; the hash table above is current." }),
		},
		[201],
	);
	console.log("updated drift issue #" + existing.number);
}

async function main(): Promise<void> {
	const lock = (await Bun.file(LOCK_PATH).json()) as SourceLock;
	if (!lock.repository || !lock.ref || !lock.snapshotCommit || !Object.keys(lock.trees ?? {}).length) {
		throw new Error("Invalid OMP source lock: " + LOCK_PATH);
	}
	const current = await currentTrees(lock);
	const drift = Object.keys(lock.trees).sort().filter(sourcePath => lock.trees[sourcePath] !== current.trees[sourcePath]);
	if (NOTIFY) await notify(lock, current.head, current.trees, drift.length > 0);
	if (drift.length === 0) {
		console.log("OMP source trees match " + lock.repository + "@" + current.head.slice(0, 12));
		return;
	}
	console.error("OMP development snapshot drifted at " + drift.join(", "));
	for (const sourcePath of drift) {
		console.error("  " + sourcePath + ": " + lock.trees[sourcePath] + " -> " + (current.trees[sourcePath] ?? "missing"));
	}
	if (!NOTIFY) process.exitCode = 1;
}

await main().catch(error => {
	console.error(error instanceof Error ? error.message : String(error));
	process.exitCode = 1;
});
