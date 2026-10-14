import { describe, expect, test } from "bun:test";
import { driftMarker, findNotificationIssue, type Issue, notify, notifyAction, resolvedBody, type SourceLock } from "./check-omp-source";

const REPOSITORY = "clssck/agent-plugins";
const TITLE = "OMP source baseline changed";
const lock: SourceLock = {
	repository: "can1357/oh-my-pi",
	ref: "main",
	reviewedCommit: "a".repeat(40),
	trees: { ".omp/skills": "1".repeat(40) },
	notification: { repository: REPOSITORY, assignee: "clssck", issueTitle: TITLE },
};
const drift = { ".omp/skills": "2".repeat(40) };
const marker = driftMarker(drift);

function issue(number: number, overrides: Partial<Issue> = {}): Issue {
	return { number, title: TITLE, body: null, state: "open", ...overrides };
}

interface Call {
	endpoint: string;
	method: string;
	body?: Record<string, unknown>;
}

/** Fake REST client serving `all` issues in pages of 100 and recording every other call. */
function fakeGitHub(all: Issue[]) {
	const calls: Call[] = [];
	const request = async <T>(endpoint: string, init: RequestInit, allowed: number[]): Promise<T> => {
		const method = init.method ?? "GET";
		const body = typeof init.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : undefined;
		calls.push({ endpoint, method, body });
		expect(allowed.length).toBeGreaterThan(0);
		if (method === "GET") {
			const page = Number(new URL(`https://x${endpoint}`).searchParams.get("page"));
			return all.slice((page - 1) * 100, page * 100) as T;
		}
		return { number: 999 } as T;
	};
	return { calls, request: request as <T>(endpoint: string, init: RequestInit, allowed: number[]) => Promise<T> };
}

const writes = (calls: Call[]) => calls.filter(call => call.method !== "GET");

function filler(count: number, firstNumber: number): Issue[] {
	return Array.from({ length: count }, (_, index) => issue(firstNumber + index, { title: `other ${firstNumber + index}`, state: "closed" }));
}

describe("findNotificationIssue", () => {
	test("finds an issue beyond the first 100 and requests each page", async () => {
		const target = issue(250, { state: "closed" });
		const { calls, request } = fakeGitHub([...filler(100, 1), ...filler(100, 101), target, ...filler(5, 251)]);
		expect(await findNotificationIssue(REPOSITORY, TITLE, request)).toBe(target);
		expect(calls.map(call => new URL(`https://x${call.endpoint}`).searchParams.get("page"))).toEqual(["1", "2", "3"]);
	});

	test("ignores pull requests with the same title", async () => {
		const pullRequest = issue(1, { pull_request: {} });
		const real = issue(2, { state: "closed" });
		const { request } = fakeGitHub([pullRequest, real]);
		expect(await findNotificationIssue(REPOSITORY, TITLE, request)).toBe(real);
		expect(await findNotificationIssue(REPOSITORY, TITLE, fakeGitHub([pullRequest]).request)).toBeUndefined();
	});

	test("a full final page is followed by an empty page, so nothing is missed", async () => {
		const { calls, request } = fakeGitHub(filler(100, 1));
		expect(await findNotificationIssue(REPOSITORY, TITLE, request)).toBeUndefined();
		expect(calls).toHaveLength(2);
	});

	test("with duplicates prefers an open issue, then the oldest", async () => {
		const closedOld = issue(3, { state: "closed" });
		const closedNew = issue(4, { state: "closed" });
		const openIssue = issue(5);
		expect(await findNotificationIssue(REPOSITORY, TITLE, fakeGitHub([closedOld, closedNew, openIssue]).request)).toBe(openIssue);
		expect(await findNotificationIssue(REPOSITORY, TITLE, fakeGitHub([closedOld, closedNew]).request)).toBe(closedOld);
	});
});

describe("notifyAction", () => {
	test("creates, leaves a reported or dismissed unchanged drift alone, and refreshes new drift", () => {
		expect(notifyAction(undefined, true, marker)).toBe("create");
		expect(notifyAction(issue(1, { body: marker }), true, marker)).toBe("none");
		expect(notifyAction(issue(1, { body: marker, state: "closed" }), true, marker)).toBe("none");
		expect(notifyAction(issue(1, { body: driftMarker({ ".omp/skills": "3".repeat(40) }) }), true, marker)).toBe("refresh");
		expect(notifyAction(issue(1, { body: driftMarker({ ".omp/skills": "3".repeat(40) }), state: "closed" }), true, marker)).toBe("refresh");
	});

	test("closes an open issue when resolved and clears the marker of a dismissed one", () => {
		expect(notifyAction(issue(1, { body: marker }), false, marker)).toBe("close");
		expect(notifyAction(issue(1, { body: marker, state: "closed" }), false, marker)).toBe("resolve");
		expect(notifyAction(issue(1, { body: resolvedBody(marker), state: "closed" }), false, marker)).toBe("none");
		expect(notifyAction(undefined, false, marker)).toBe("none");
	});

	test("an auto-closed issue is reopened when the same drift as its old report recurs", () => {
		const resolved = issue(1, { body: resolvedBody(`report\n\n${marker}`), state: "closed" });
		expect(resolved.body).not.toContain(marker);
		expect(notifyAction(resolved, true, marker)).toBe("refresh");
	});
});

describe("resolvedBody", () => {
	test("replaces the drift marker with the resolved marker and is idempotent", () => {
		const body = resolvedBody(`table\n\n${marker}`);
		expect(body).toContain("<!-- omp-source-resolved -->");
		expect(body).not.toContain("omp-source-current");
		expect(resolvedBody(body)).toBe(body);
		expect(resolvedBody(null)).toBe("<!-- omp-source-resolved -->");
	});
});

describe("notify", () => {
	test("refuses to run outside the notification repository", async () => {
		await expect(notify(lock, "b".repeat(40), drift, true, fakeGitHub([]).request, "someone/else")).rejects.toThrow("Refusing to notify");
	});

	test("reuses a closed issue on a later page instead of opening a duplicate", async () => {
		const existing = issue(150, { state: "closed", body: resolvedBody(`old\n\n${marker}`) });
		const { calls, request } = fakeGitHub([...filler(100, 1), ...filler(49, 101), existing]);
		await notify(lock, "b".repeat(40), drift, true, request, REPOSITORY);
		const [patch, comment] = writes(calls);
		expect(writes(calls).some(call => call.method === "POST" && call.endpoint.endsWith("/issues"))).toBe(false);
		expect(patch.endpoint).toBe(`/repos/${REPOSITORY}/issues/150`);
		expect(patch.body).toMatchObject({ state: "open", assignees: ["clssck"] });
		expect(String(patch.body?.body)).toContain(marker);
		expect(comment.endpoint).toBe(`/repos/${REPOSITORY}/issues/150/comments`);
	});

	test("an unchanged dismissed drift writes nothing", async () => {
		const { calls, request } = fakeGitHub([issue(7, { state: "closed", body: marker })]);
		await notify(lock, "b".repeat(40), drift, true, request, REPOSITORY);
		expect(writes(calls)).toEqual([]);
	});

	test("a baseline match clears stale markers on every duplicate so an older recurrence is not dismissed", async () => {
		const olderDrift = { ".omp/skills": "3".repeat(40) };
		const olderMarker = driftMarker(olderDrift);
		const closedOld = issue(3, { state: "closed", body: `old report\n\n${olderMarker}` });
		const openNew = issue(4, { body: `new report\n\n${marker}` });
		const resolved = issue(5, { state: "closed", body: resolvedBody("done") });

		const match = fakeGitHub([closedOld, openNew, resolved]);
		await notify(lock, "b".repeat(40), lock.trees, false, match.request, REPOSITORY);
		const patches = writes(match.calls);
		expect(patches.map(call => call.endpoint)).toEqual([`/repos/${REPOSITORY}/issues/3`, `/repos/${REPOSITORY}/issues/4`]);
		expect(patches[0].body).not.toHaveProperty("state");
		expect(patches[1].body).toMatchObject({ state: "closed" });
		for (const patch of patches) {
			expect(String(patch.body?.body)).toContain("<!-- omp-source-resolved -->");
			expect(String(patch.body?.body)).not.toContain("omp-source-current");
		}

		// Both issues now carry the state the baseline match wrote; the older drift recurs and must be reported.
		const afterMatch = [
			issue(3, { state: "closed", body: String(patches[0].body?.body) }),
			issue(4, { state: "closed", body: String(patches[1].body?.body) }),
			resolved,
		];
		const recurrence = fakeGitHub(afterMatch);
		await notify(lock, "b".repeat(40), olderDrift, true, recurrence.request, REPOSITORY);
		const [refresh] = writes(recurrence.calls);
		expect(refresh.endpoint).toBe(`/repos/${REPOSITORY}/issues/3`);
		expect(refresh.body).toMatchObject({ state: "open", assignees: ["clssck"] });
		expect(String(refresh.body?.body)).toContain(olderMarker);
	});

	test("resolving closes the open issue and records the resolved state in its body", async () => {
		const { calls, request } = fakeGitHub([issue(7, { body: `report\n\n${marker}` })]);
		await notify(lock, "b".repeat(40), lock.trees, false, request, REPOSITORY);
		const [patch] = writes(calls);
		expect(patch.body).toMatchObject({ state: "closed" });
		expect(String(patch.body?.body)).toContain("<!-- omp-source-resolved -->");
		expect(String(patch.body?.body)).not.toContain("omp-source-current");
	});

	test("opens an issue when none exists on any page", async () => {
		const { calls, request } = fakeGitHub(filler(3, 1));
		await notify(lock, "b".repeat(40), drift, true, request, REPOSITORY);
		const [created] = writes(calls);
		expect(created.method).toBe("POST");
		expect(created.endpoint).toBe(`/repos/${REPOSITORY}/issues`);
		expect(String(created.body?.body)).toContain(marker);
	});
});
