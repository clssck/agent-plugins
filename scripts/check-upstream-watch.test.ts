import { describe, expect, test } from "bun:test";
import * as path from "node:path";
import {
	changedSources,
	compareUrl,
	driftMarker,
	fetchStates,
	type Issue,
	isChanged,
	issueBody,
	NOTIFICATION_AUTHOR,
	notify,
	notifyAction,
	OWNERSHIP_MARKER,
	parseConfig,
	type Request,
	resolvedBody,
	scanIssues,
	type SourceState,
	type WatchConfig,
	type WatchSource,
} from "./check-upstream-watch";

const REPOSITORY = "clssck/agent-plugins";
const TITLE = "Emil design skills upstream changed";
const REVIEWED = "2d228630ba1446365f614a108cb8252f1feda202";
const LATEST = "b".repeat(40);

const source: WatchSource = {
	name: "emilkowalski-skills",
	repository: "emilkowalski/skills",
	ref: "main",
	path: "skills",
	reviewedCommit: REVIEWED,
	target: "packs/clssck/skills",
	issueTitle: TITLE,
};
const config: WatchConfig = { repository: REPOSITORY, assignee: "clssck", sources: [source] };
const clean: SourceState = { latest: REVIEWED, reviewed: REVIEWED };
const drift: SourceState = { latest: LATEST, reviewed: REVIEWED };
const marker = driftMarker(source, drift);

/** An issue this automation owns: authored by the workflow bot and carrying the ownership marker. */
function issue(number: number, overrides: Partial<Issue> = {}): Issue {
	const body = overrides.body ? `${overrides.body}\n\n${OWNERSHIP_MARKER}` : OWNERSHIP_MARKER;
	return { number, title: TITLE, state: "open", user: { login: NOTIFICATION_AUTHOR }, ...overrides, body };
}

/** A same-title issue the automation does not own; `body` is used verbatim. */
function foreign(number: number, overrides: Partial<Issue> = {}): Issue {
	return { number, title: TITLE, body: null, state: "open", user: { login: "someone-else" }, ...overrides };
}

/** A GitHub Actions run on main in the configured repository. */
const MAIN_ENV = { GITHUB_REPOSITORY: REPOSITORY, GITHUB_ACTIONS: "true", GITHUB_REF: "refs/heads/main" };

interface Call {
	endpoint: string;
	method: string;
	body?: Record<string, unknown>;
}

/** Fake REST client serving `all` issues in pages of 100 and recording every call. */
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
	return { calls, request: request as Request };
}

const writes = (calls: Call[]) => calls.filter(call => call.method !== "GET");

function filler(count: number, firstNumber: number): Issue[] {
	return Array.from({ length: count }, (_, index) => issue(firstNumber + index, { title: `other ${firstNumber + index}`, state: "closed" }));
}

function rawConfig(overrides: Record<string, unknown> = {}, sourceOverrides: Record<string, unknown> = {}) {
	return { repository: REPOSITORY, assignee: "clssck", sources: [{ ...source, ...sourceOverrides }], ...overrides };
}

describe("parseConfig", () => {
	test("the shipped upstream-watch.json pins the vendored Emil skills", async () => {
		const parsed = parseConfig(await Bun.file(path.resolve(import.meta.dir, "..", "upstream-watch.json")).json());
		expect(parsed).toEqual(config);
	});

	test("accepts a valid config", () => {
		expect(parseConfig(rawConfig())).toEqual(config);
	});

	test("rejects a non-object, missing sources, and an empty source list", () => {
		expect(() => parseConfig(null)).toThrow("expected an object");
		expect(() => parseConfig([])).toThrow("expected an object");
		expect(() => parseConfig({ repository: REPOSITORY, assignee: "clssck" })).toThrow("non-empty array");
		expect(() => parseConfig(rawConfig({ sources: [] }))).toThrow("non-empty array");
		expect(() => parseConfig(rawConfig({ sources: ["emil"] }))).toThrow("must be an object");
	});

	test("rejects empty or missing fields", () => {
		expect(() => parseConfig(rawConfig({ assignee: " " }))).toThrow("config.assignee");
		expect(() => parseConfig(rawConfig({ repository: undefined }))).toThrow("config.repository");
		for (const key of ["name", "repository", "ref", "path", "reviewedCommit", "target", "issueTitle"]) {
			expect(() => parseConfig(rawConfig({}, { [key]: "" }))).toThrow(`sources[0].${key}`);
			expect(() => parseConfig(rawConfig({}, { [key]: undefined }))).toThrow(`sources[0].${key}`);
		}
	});

	test("rejects malformed repositories and commits", () => {
		expect(() => parseConfig(rawConfig({ repository: "agent-plugins" }))).toThrow("owner/name");
		expect(() => parseConfig(rawConfig({}, { repository: "emilkowalski" }))).toThrow("owner/name");
		expect(() => parseConfig(rawConfig({}, { repository: "a/b/c" }))).toThrow("owner/name");
		expect(() => parseConfig(rawConfig({}, { reviewedCommit: "main" }))).toThrow("40-character");
		expect(() => parseConfig(rawConfig({}, { reviewedCommit: REVIEWED.toUpperCase() }))).toThrow("40-character");
		expect(() => parseConfig(rawConfig({}, { reviewedCommit: REVIEWED.slice(0, 39) }))).toThrow("40-character");
	});

	test("rejects absolute and parent-escaping paths", () => {
		expect(() => parseConfig(rawConfig({}, { path: "/skills" }))).toThrow("sources[0].path");
		expect(() => parseConfig(rawConfig({}, { path: "skills/../x" }))).toThrow("sources[0].path");
		expect(() => parseConfig(rawConfig({}, { target: "../outside" }))).toThrow("sources[0].target");
		expect(() => parseConfig(rawConfig({}, { target: "packs//skills" }))).toThrow("sources[0].target");
	});

	test("rejects duplicate source names and issue titles", () => {
		const other = { ...source, name: "other", issueTitle: "Other changed" };
		expect(() => parseConfig(rawConfig({ sources: [source, { ...other, name: source.name }] }))).toThrow("duplicate source name");
		expect(() => parseConfig(rawConfig({ sources: [source, { ...other, issueTitle: TITLE }] }))).toThrow("duplicate issueTitle");
		expect(parseConfig(rawConfig({ sources: [source, other] })).sources).toHaveLength(2);
	});
});

describe("fetchStates", () => {
	const node = (oid: string) => ({ history: { nodes: [{ oid }] } });

	test("queries history(first: 1, path: ...) on the ref and at the reviewed commit", async () => {
		let query = "";
		const states = await fetchStates([source], async <T>(q: string) => {
			query = q;
			return { s0: { head: node(LATEST), reviewed: node(REVIEWED) } } as T;
		});
		expect(states).toEqual([drift]);
		expect(query).toContain('repository(owner: "emilkowalski", name: "skills")');
		expect(query).toContain('object(expression: "main")');
		expect(query).toContain(`object(oid: "${REVIEWED}")`);
		expect(query.match(/history\(first: 1, path: "skills"\)/g)).toHaveLength(2);
	});

	test("aliases every source separately", async () => {
		const second: WatchSource = { ...source, name: "second", repository: "someone/else", issueTitle: "Second", reviewedCommit: "c".repeat(40) };
		const states = await fetchStates([source, second], async <T>() => {
			return {
				s0: { head: node(LATEST), reviewed: node(REVIEWED) },
				s1: { head: node("d".repeat(40)), reviewed: node("d".repeat(40)) },
			} as T;
		});
		expect(states).toEqual([drift, { latest: "d".repeat(40), reviewed: "d".repeat(40) }]);
	});

	test("fails when the ref has no commit for the path or the reviewed commit is unknown", async () => {
		const empty = { history: { nodes: [] } };
		await expect(fetchStates([source], async <T>() => ({ s0: { head: empty, reviewed: node(REVIEWED) } }) as T)).rejects.toThrow("no commit touching main:skills");
		await expect(fetchStates([source], async <T>() => ({ s0: { head: node(LATEST), reviewed: null } }) as T)).rejects.toThrow("no reviewed commit");
		await expect(fetchStates([source], async <T>() => ({ s0: null }) as T)).rejects.toThrow("no commit touching");
	});
});

describe("changed detection", () => {
	test("changed only when the path has a commit newer than the reviewed one", () => {
		expect(isChanged(clean)).toBe(false);
		expect(isChanged(drift)).toBe(true);
	});

	test("a reviewed commit that did not itself touch the path is not drift while the path is unchanged", () => {
		expect(isChanged({ latest: "e".repeat(40), reviewed: "e".repeat(40) })).toBe(false);
	});

	test("selects only the changed sources", () => {
		const other: WatchSource = { ...source, name: "other", issueTitle: "Other changed" };
		expect(changedSources([source, other], [clean, drift])).toEqual([other]);
		expect(changedSources([source, other], [clean, clean])).toEqual([]);
		expect(changedSources([source, other], [drift, drift])).toEqual([source, other]);
	});
});

describe("issueBody", () => {
	const body = issueBody(config, source, drift, marker);

	test("names the source, repository, pinned and latest commits, and target", () => {
		expect(body.startsWith("@clssck ")).toBe(true);
		expect(body).toContain("emilkowalski-skills");
		expect(body).toContain("emilkowalski/skills");
		expect(body).toContain("main:skills");
		expect(body).toContain(`[${REVIEWED.slice(0, 12)}](https://github.com/emilkowalski/skills/commit/${REVIEWED})`);
		expect(body).toContain(`[${LATEST.slice(0, 12)}](https://github.com/emilkowalski/skills/commit/${LATEST})`);
		expect(body).toContain("`packs/clssck/skills`");
	});

	test("includes the compare URL", () => {
		expect(compareUrl(source, LATEST)).toBe(`https://github.com/emilkowalski/skills/compare/${REVIEWED}...${LATEST}`);
		expect(body).toContain(`Compare: https://github.com/emilkowalski/skills/compare/${REVIEWED}...${LATEST}`);
	});

	test("gives the review, port, gate, pin, and close instructions", () => {
		expect(body).toContain("Review the upstream diff");
		expect(body).toContain("Port or adapt");
		expect(body).toContain("bun test scripts");
		expect(body).toContain("bun scripts/sync.ts --check");
		expect(body).toContain("`reviewedCommit` for `emilkowalski-skills` in `upstream-watch.json`");
		expect(body).toContain("Close this issue");
	});

	test("ends with the upstream-watch drift marker, never the OMP marker", () => {
		expect(body.endsWith(marker)).toBe(true);
		expect(marker).toMatch(/^<!-- upstream-watch-current:[0-9a-f]{64} -->$/);
		expect(body).not.toContain("omp-source");
	});
});

describe("driftMarker", () => {
	test("is deterministic and varies with the source and latest commit", () => {
		expect(driftMarker(source, drift)).toBe(driftMarker(source, { ...drift }));
		expect(driftMarker(source, drift)).not.toBe(driftMarker(source, { latest: "c".repeat(40), reviewed: REVIEWED }));
		expect(driftMarker(source, drift)).not.toBe(driftMarker({ ...source, name: "other" }, drift));
	});
});

describe("scanIssues", () => {
	test("finds an issue beyond the first 100 and requests each page", async () => {
		const target = issue(250, { state: "closed" });
		const { calls, request } = fakeGitHub([...filler(100, 1), ...filler(100, 101), target, ...filler(5, 251)]);
		expect((await scanIssues(REPOSITORY, TITLE, request)).canonical).toBe(target);
		expect(calls.map(call => new URL(`https://x${call.endpoint}`).searchParams.get("page"))).toEqual(["1", "2", "3"]);
	});

	test("ignores pull requests with the same title", async () => {
		const pullRequest = issue(1, { pull_request: {} });
		const real = issue(2, { state: "closed" });
		expect((await scanIssues(REPOSITORY, TITLE, fakeGitHub([pullRequest, real]).request)).matches).toEqual([real]);
		expect((await scanIssues(REPOSITORY, TITLE, fakeGitHub([pullRequest]).request)).canonical).toBeUndefined();
	});

	test("a full final page is followed by an empty page, so nothing is missed", async () => {
		const { calls, request } = fakeGitHub(filler(100, 1));
		expect((await scanIssues(REPOSITORY, TITLE, request)).canonical).toBeUndefined();
		expect(calls).toHaveLength(2);
	});

	test("with duplicates prefers an open issue, then the oldest", async () => {
		const closedOld = issue(3, { state: "closed" });
		const closedNew = issue(4, { state: "closed" });
		const openIssue = issue(5);
		expect((await scanIssues(REPOSITORY, TITLE, fakeGitHub([closedOld, closedNew, openIssue]).request)).canonical).toBe(openIssue);
		expect((await scanIssues(REPOSITORY, TITLE, fakeGitHub([closedOld, closedNew]).request)).canonical).toBe(closedOld);
	});
});

describe("notifyAction", () => {
	const otherMarker = driftMarker(source, { latest: "c".repeat(40), reviewed: REVIEWED });

	test("creates, leaves a reported or dismissed unchanged drift alone, and refreshes new drift", () => {
		expect(notifyAction(undefined, true, marker)).toBe("create");
		expect(notifyAction(issue(1, { body: marker }), true, marker)).toBe("none");
		expect(notifyAction(issue(1, { body: marker, state: "closed" }), true, marker)).toBe("none");
		expect(notifyAction(issue(1, { body: otherMarker }), true, marker)).toBe("refresh");
		expect(notifyAction(issue(1, { body: otherMarker, state: "closed" }), true, marker)).toBe("refresh");
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

	test("ignores the OMP baseline marker", () => {
		expect(notifyAction(issue(1, { body: "<!-- omp-source-current:abc123 -->", state: "closed" }), false, marker)).toBe("none");
	});
});

describe("resolvedBody", () => {
	test("replaces the drift marker with the resolved marker and is idempotent", () => {
		const body = resolvedBody(`table\n\n${marker}`);
		expect(body).toContain("<!-- upstream-watch-resolved -->");
		expect(body).not.toContain("upstream-watch-current");
		expect(resolvedBody(body)).toBe(body);
		expect(resolvedBody(null)).toBe("<!-- upstream-watch-resolved -->");
	});
});

describe("notify", () => {
	test("refuses to run outside the configured repository before any request", async () => {
		const { calls, request } = fakeGitHub([]);
		await expect(notify(config, [drift], request, { ...MAIN_ENV, GITHUB_REPOSITORY: "someone/else" })).rejects.toThrow("Refusing to notify");
		await expect(notify(config, [drift], request, {})).rejects.toThrow("<unset>");
		expect(calls).toEqual([]);
	});

	test("refuses a GitHub Actions run on any ref but main before any request", async () => {
		const { calls, request } = fakeGitHub([issue(7, { body: marker })]);
		for (const ref of ["refs/heads/feature", "refs/pull/12/merge", "refs/tags/v1", undefined]) {
			await expect(notify(config, [drift], request, { ...MAIN_ENV, GITHUB_REF: ref })).rejects.toThrow("Refusing to notify");
			await expect(notify(config, [clean], request, { ...MAIN_ENV, GITHUB_REF: ref })).rejects.toThrow("Refusing to notify");
		}
		expect(calls).toEqual([]);
	});

	test("a run outside GitHub Actions may notify from any local ref", async () => {
		const { calls, request } = fakeGitHub([]);
		await notify(config, [drift], request, { GITHUB_REPOSITORY: REPOSITORY, GITHUB_REF: "refs/heads/feature" });
		expect(writes(calls)).toHaveLength(1);
	});

	test("opens one assigned issue with the drift marker when none exists on any page", async () => {
		const { calls, request } = fakeGitHub(filler(3, 1));
		await notify(config, [drift], request, MAIN_ENV);
		const [created] = writes(calls);
		expect(writes(calls)).toHaveLength(1);
		expect(created.method).toBe("POST");
		expect(created.endpoint).toBe(`/repos/${REPOSITORY}/issues`);
		expect(created.body).toMatchObject({ title: TITLE, assignees: ["clssck"] });
		expect(String(created.body?.body)).toContain(marker);
		expect(String(created.body?.body)).toContain(compareUrl(source, LATEST));
	});

	test("an already reported drift writes nothing (idempotent)", async () => {
		const { calls, request } = fakeGitHub([issue(7, { body: issueBody(config, source, drift, marker) })]);
		await notify(config, [drift], request, MAIN_ENV);
		expect(writes(calls)).toEqual([]);
	});

	test("an unchanged dismissed drift writes nothing", async () => {
		const { calls, request } = fakeGitHub([issue(7, { state: "closed", body: marker })]);
		await notify(config, [drift], request, MAIN_ENV);
		expect(writes(calls)).toEqual([]);
	});

	test("refreshes and reopens a closed issue on a later page for new drift instead of opening a duplicate", async () => {
		const existing = issue(150, { state: "closed", body: `old\n\n${driftMarker(source, { latest: "c".repeat(40), reviewed: REVIEWED })}` });
		const { calls, request } = fakeGitHub([...filler(100, 1), ...filler(49, 101), existing]);
		await notify(config, [drift], request, MAIN_ENV);
		const [patch, comment] = writes(calls);
		expect(writes(calls)).toHaveLength(2);
		expect(patch.method).toBe("PATCH");
		expect(patch.endpoint).toBe(`/repos/${REPOSITORY}/issues/150`);
		expect(patch.body).toMatchObject({ state: "open", assignees: ["clssck"] });
		expect(String(patch.body?.body)).toContain(marker);
		expect(comment.method).toBe("POST");
		expect(comment.endpoint).toBe(`/repos/${REPOSITORY}/issues/150/comments`);
		expect(String(comment.body?.body)).toContain("@clssck");
	});

	test("a recurrence equal to an older auto-closed report is refreshed", async () => {
		const { calls, request } = fakeGitHub([issue(9, { state: "closed", body: resolvedBody(`report\n\n${marker}`) })]);
		await notify(config, [drift], request, MAIN_ENV);
		const [patch] = writes(calls);
		expect(patch.endpoint).toBe(`/repos/${REPOSITORY}/issues/9`);
		expect(patch.body).toMatchObject({ state: "open" });
	});

	test("resolving closes the open issue and records the resolved state in its body", async () => {
		const { calls, request } = fakeGitHub([issue(7, { body: `report\n\n${marker}` })]);
		await notify(config, [clean], request, MAIN_ENV);
		const [patch] = writes(calls);
		expect(writes(calls)).toHaveLength(1);
		expect(patch.method).toBe("PATCH");
		expect(patch.endpoint).toBe(`/repos/${REPOSITORY}/issues/7`);
		expect(patch.body).toMatchObject({ state: "closed" });
		expect(String(patch.body?.body)).toContain("<!-- upstream-watch-resolved -->");
		expect(String(patch.body?.body)).not.toContain("upstream-watch-current");
	});

	test("nothing changed and no issue writes nothing", async () => {
		const { calls, request } = fakeGitHub(filler(3, 1));
		await notify(config, [clean], request, MAIN_ENV);
		expect(writes(calls)).toEqual([]);
	});

	test("a resolved state clears stale markers on every duplicate so an older recurrence is not dismissed", async () => {
		const olderDrift: SourceState = { latest: "c".repeat(40), reviewed: REVIEWED };
		const olderMarker = driftMarker(source, olderDrift);
		const closedOld = issue(3, { state: "closed", body: `old report\n\n${olderMarker}` });
		const openNew = issue(4, { body: `new report\n\n${marker}` });
		const resolved = issue(5, { state: "closed", body: resolvedBody("done") });

		const match = fakeGitHub([closedOld, openNew, resolved]);
		await notify(config, [clean], match.request, MAIN_ENV);
		const patches = writes(match.calls);
		expect(patches.map(call => call.endpoint)).toEqual([`/repos/${REPOSITORY}/issues/3`, `/repos/${REPOSITORY}/issues/4`]);
		expect(patches[0].body).not.toHaveProperty("state");
		expect(patches[1].body).toMatchObject({ state: "closed" });
		for (const patch of patches) {
			expect(String(patch.body?.body)).toContain("<!-- upstream-watch-resolved -->");
			expect(String(patch.body?.body)).not.toContain("upstream-watch-current");
		}

		// Both issues now carry the state the resolution wrote; the older drift recurs and must be reported.
		const afterMatch = [
			issue(3, { state: "closed", body: String(patches[0].body?.body) }),
			issue(4, { state: "closed", body: String(patches[1].body?.body) }),
			resolved,
		];
		const recurrence = fakeGitHub(afterMatch);
		await notify(config, [olderDrift], recurrence.request, MAIN_ENV);
		const [refresh] = writes(recurrence.calls);
		expect(refresh.endpoint).toBe(`/repos/${REPOSITORY}/issues/3`);
		expect(refresh.body).toMatchObject({ state: "open", assignees: ["clssck"] });
		expect(String(refresh.body?.body)).toContain(olderMarker);
	});

	test("handles each source with its own issue title", async () => {
		const other: WatchSource = { ...source, name: "other", issueTitle: "Other changed" };
		const two: WatchConfig = { ...config, sources: [source, other] };
		const { calls, request } = fakeGitHub([issue(1, { title: "Other changed", body: driftMarker(other, drift) })]);
		await notify(two, [drift, drift], request, MAIN_ENV);
		const [created] = writes(calls);
		expect(writes(calls)).toHaveLength(1);
		expect(created.body).toMatchObject({ title: TITLE });
	});

	test("a foreign same-title issue is never mutated and does not suppress creating an owned issue", async () => {
		const lookalikes = [
			foreign(1, { body: marker }),
			foreign(2, { body: `${marker}\n\n${OWNERSHIP_MARKER}` }),
			foreign(3, { body: OWNERSHIP_MARKER, user: { login: "github-actions" } }),
			foreign(4, { body: OWNERSHIP_MARKER, user: null }),
			foreign(5, { body: marker, user: { login: NOTIFICATION_AUTHOR } }),
		];
		const { calls, request } = fakeGitHub(lookalikes);
		await notify(config, [drift], request, MAIN_ENV);
		const [created, ...rest] = writes(calls);
		expect(rest).toEqual([]);
		expect(created.method).toBe("POST");
		expect(created.endpoint).toBe(`/repos/${REPOSITORY}/issues`);
		expect(String(created.body?.body)).toContain(OWNERSHIP_MARKER);
	});

	test("a resolved state never closes or rewrites a foreign same-title issue", async () => {
		const { calls, request } = fakeGitHub([
			foreign(1, { body: `report\n\n${marker}` }),
			foreign(2, { state: "closed", body: `report\n\n${marker}` }),
			foreign(3, { body: `report\n\n${marker}`, user: { login: NOTIFICATION_AUTHOR } }),
		]);
		await notify(config, [clean], request, MAIN_ENV);
		expect(writes(calls)).toEqual([]);
	});

	test("new drift refreshes the owned issue and leaves a foreign duplicate alone", async () => {
		const oldMarker = driftMarker(source, { latest: "c".repeat(40), reviewed: REVIEWED });
		const { calls, request } = fakeGitHub([foreign(1, { body: oldMarker }), issue(2, { state: "closed", body: oldMarker })]);
		await notify(config, [drift], request, MAIN_ENV);
		const [patch, comment, ...rest] = writes(calls);
		expect(rest).toEqual([]);
		expect(patch.endpoint).toBe(`/repos/${REPOSITORY}/issues/2`);
		expect(patch.body).toMatchObject({ state: "open", assignees: ["clssck"] });
		expect(String(patch.body?.body)).toContain(marker);
		expect(String(patch.body?.body)).toContain(OWNERSHIP_MARKER);
		expect(comment.endpoint).toBe(`/repos/${REPOSITORY}/issues/2/comments`);
	});

	test("a resolved state closes only owned duplicates and keeps their ownership", async () => {
		const { calls, request } = fakeGitHub([
			foreign(1, { body: `report\n\n${marker}` }),
			issue(2, { body: `report\n\n${marker}` }),
			foreign(3, { body: `report\n\n${marker}` }),
			issue(4, { state: "closed", body: `report\n\n${marker}` }),
		]);
		await notify(config, [clean], request, MAIN_ENV);
		const patches = writes(calls);
		expect(patches.map(call => call.endpoint)).toEqual([`/repos/${REPOSITORY}/issues/2`, `/repos/${REPOSITORY}/issues/4`]);
		expect(patches[0].body).toMatchObject({ state: "closed" });
		expect(patches[1].body).not.toHaveProperty("state");
		for (const patch of patches) {
			expect(String(patch.body?.body)).toContain(OWNERSHIP_MARKER);
			expect(String(patch.body?.body)).toContain("<!-- upstream-watch-resolved -->");
		}
	});

	test("an unchanged owned report beside a foreign same-title issue writes nothing", async () => {
		const { calls, request } = fakeGitHub([foreign(1), issue(2, { body: marker })]);
		await notify(config, [drift], request, MAIN_ENV);
		expect(writes(calls)).toEqual([]);
	});

	test("every issue body this automation writes is recognised as owned on the next run", async () => {
		const first = fakeGitHub([]);
		await notify(config, [drift], first.request, MAIN_ENV);
		const created = String(writes(first.calls)[0].body?.body);
		const second = fakeGitHub([{ number: 5, title: TITLE, body: created, state: "open", user: { login: NOTIFICATION_AUTHOR } }]);
		await notify(config, [drift], second.request, MAIN_ENV);
		expect(writes(second.calls)).toEqual([]);
	});
});
