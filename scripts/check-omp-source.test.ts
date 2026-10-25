import { describe, expect, test } from "bun:test";
import {
  driftMarker,
  findNotificationIssue,
  type Issue,
  NOTIFICATION_AUTHOR,
  notify,
  notifyAction,
  OWNERSHIP_MARKER,
  resolvedBody,
  type SourceLock,
} from "./check-omp-source";

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

/** An issue this automation owns: authored by the workflow bot and carrying the ownership marker. */
function issue(number: number, overrides: Partial<Issue> = {}): Issue {
  const body = overrides.body ? `${overrides.body}\n\n${OWNERSHIP_MARKER}` : OWNERSHIP_MARKER;
  return {
    number,
    title: TITLE,
    state: "open",
    user: { login: NOTIFICATION_AUTHOR },
    ...overrides,
    body,
  };
}

/** A same-title issue the automation does not own; `body` is used verbatim. */
function foreign(number: number, overrides: Partial<Issue> = {}): Issue {
  return {
    number,
    title: TITLE,
    body: null,
    state: "open",
    user: { login: "someone-else" },
    ...overrides,
  };
}

/** A GitHub Actions run on main in the notification repository. */
const MAIN_ENV = {
  GITHUB_REPOSITORY: REPOSITORY,
  GITHUB_ACTIONS: "true",
  GITHUB_REF: "refs/heads/main",
};

interface Call {
  endpoint: string;
  method: string;
  body: unknown;
}

function must<T>(value: T | undefined): T {
  if (value === undefined) {
    throw new Error("unexpected undefined");
  }
  return value;
}

/** The `body` string a recorded write sent in its JSON payload. */
function bodyText(call: Call): string {
  const sent = call.body;
  if (
    typeof sent === "object" &&
    sent !== null &&
    "body" in sent &&
    typeof sent.body === "string"
  ) {
    return sent.body;
  }
  throw new Error(`${call.method} ${call.endpoint} sent no body text`);
}

/** Fake REST client serving `all` issues in pages of 100 and recording every other call. */
function fakeGitHub(all: Issue[]) {
  const calls: Call[] = [];
  const request = (endpoint: string, init: RequestInit, allowed: number[]): Promise<unknown> => {
    const method = init.method ?? "GET";
    const body: unknown = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ endpoint, method, body });
    expect(allowed.length).toBeGreaterThan(0);
    if (method === "GET") {
      const page = Number(new URL(`https://x${endpoint}`).searchParams.get("page"));
      return Promise.resolve(all.slice((page - 1) * 100, page * 100));
    }
    return Promise.resolve({ number: 999 });
  };
  return { calls, request };
}

const writes = (calls: Call[]) => calls.filter((call) => call.method !== "GET");

function filler(count: number, firstNumber: number): Issue[] {
  return Array.from({ length: count }, (_, index) =>
    issue(firstNumber + index, { title: `other ${firstNumber + index}`, state: "closed" }),
  );
}

describe("findNotificationIssue", () => {
  test("finds an issue beyond the first 100 and requests each page", async () => {
    const target = issue(250, { state: "closed" });
    const { calls, request } = fakeGitHub([
      ...filler(100, 1),
      ...filler(100, 101),
      target,
      ...filler(5, 251),
    ]);
    expect(await findNotificationIssue(REPOSITORY, TITLE, request)).toBe(target);
    expect(
      calls.map((call) => new URL(`https://x${call.endpoint}`).searchParams.get("page")),
    ).toEqual(["1", "2", "3"]);
  });

  test("ignores pull requests with the same title", async () => {
    const pullRequest = issue(1, { pull_request: {} });
    const real = issue(2, { state: "closed" });
    const { request } = fakeGitHub([pullRequest, real]);
    expect(await findNotificationIssue(REPOSITORY, TITLE, request)).toBe(real);
    expect(
      await findNotificationIssue(REPOSITORY, TITLE, fakeGitHub([pullRequest]).request),
    ).toBeUndefined();
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
    expect(
      await findNotificationIssue(
        REPOSITORY,
        TITLE,
        fakeGitHub([closedOld, closedNew, openIssue]).request,
      ),
    ).toBe(openIssue);
    expect(
      await findNotificationIssue(REPOSITORY, TITLE, fakeGitHub([closedOld, closedNew]).request),
    ).toBe(closedOld);
  });

  test("skips foreign same-title issues, whatever their body or author", async () => {
    const owned = issue(9, { state: "closed" });
    const lookalikes = [
      foreign(1, { body: marker }),
      foreign(2, { body: OWNERSHIP_MARKER }),
      foreign(3, { body: OWNERSHIP_MARKER, user: null }),
      foreign(4, { body: marker, user: { login: NOTIFICATION_AUTHOR } }),
    ];
    expect(
      await findNotificationIssue(REPOSITORY, TITLE, fakeGitHub(lookalikes).request),
    ).toBeUndefined();
    expect(
      await findNotificationIssue(REPOSITORY, TITLE, fakeGitHub([...lookalikes, owned]).request),
    ).toBe(owned);
  });
});

describe("notifyAction", () => {
  test("creates, leaves a reported or dismissed unchanged drift alone, and refreshes new drift", () => {
    expect(notifyAction(undefined, true, marker)).toBe("create");
    expect(notifyAction(issue(1, { body: marker }), true, marker)).toBe("none");
    expect(notifyAction(issue(1, { body: marker, state: "closed" }), true, marker)).toBe("none");
    expect(
      notifyAction(
        issue(1, { body: driftMarker({ ".omp/skills": "3".repeat(40) }) }),
        true,
        marker,
      ),
    ).toBe("refresh");
    expect(
      notifyAction(
        issue(1, { body: driftMarker({ ".omp/skills": "3".repeat(40) }), state: "closed" }),
        true,
        marker,
      ),
    ).toBe("refresh");
  });

  test("closes an open issue when resolved and clears the marker of a dismissed one", () => {
    expect(notifyAction(issue(1, { body: marker }), false, marker)).toBe("close");
    expect(notifyAction(issue(1, { body: marker, state: "closed" }), false, marker)).toBe(
      "resolve",
    );
    expect(
      notifyAction(issue(1, { body: resolvedBody(marker), state: "closed" }), false, marker),
    ).toBe("none");
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
  test("refuses to run outside the notification repository before any request", async () => {
    const { calls, request } = fakeGitHub([]);
    await expect(
      notify(lock, "b".repeat(40), drift, true, request, {
        ...MAIN_ENV,
        GITHUB_REPOSITORY: "someone/else",
      }),
    ).rejects.toThrow("Refusing to notify");
    await expect(notify(lock, "b".repeat(40), drift, true, request, {})).rejects.toThrow("<unset>");
    expect(calls).toEqual([]);
  });

  test("refuses a GitHub Actions run on any ref but main before any request", async () => {
    const { calls, request } = fakeGitHub([issue(7, { body: marker })]);
    for (const ref of ["refs/heads/feature", "refs/pull/12/merge", "refs/tags/v1", undefined]) {
      await expect(
        notify(lock, "b".repeat(40), drift, true, request, { ...MAIN_ENV, GITHUB_REF: ref }),
      ).rejects.toThrow("Refusing to notify");
      await expect(
        notify(lock, "b".repeat(40), lock.trees, false, request, { ...MAIN_ENV, GITHUB_REF: ref }),
      ).rejects.toThrow("Refusing to notify");
    }
    expect(calls).toEqual([]);
  });

  test("a run outside GitHub Actions may notify from any local ref", async () => {
    const { calls, request } = fakeGitHub([]);
    await notify(lock, "b".repeat(40), drift, true, request, {
      GITHUB_REPOSITORY: REPOSITORY,
      GITHUB_REF: "refs/heads/feature",
    });
    expect(writes(calls)).toHaveLength(1);
  });

  test("reuses a closed issue on a later page instead of opening a duplicate", async () => {
    const existing = issue(150, { state: "closed", body: resolvedBody(`old\n\n${marker}`) });
    const { calls, request } = fakeGitHub([...filler(100, 1), ...filler(49, 101), existing]);
    await notify(lock, "b".repeat(40), drift, true, request, MAIN_ENV);
    const written = writes(calls);
    const patch = must(written[0]);
    const comment = must(written[1]);
    expect(
      written.some((call) => call.method === "POST" && call.endpoint.endsWith("/issues")),
    ).toBe(false);
    expect(patch.endpoint).toBe(`/repos/${REPOSITORY}/issues/150`);
    expect(patch.body).toMatchObject({ state: "open", assignees: ["clssck"] });
    expect(bodyText(patch)).toContain(marker);
    expect(comment.endpoint).toBe(`/repos/${REPOSITORY}/issues/150/comments`);
  });

  test("an unchanged dismissed drift writes nothing", async () => {
    const { calls, request } = fakeGitHub([issue(7, { state: "closed", body: marker })]);
    await notify(lock, "b".repeat(40), drift, true, request, MAIN_ENV);
    expect(writes(calls)).toEqual([]);
  });

  test("a baseline match clears stale markers on every duplicate so an older recurrence is not dismissed", async () => {
    const olderDrift = { ".omp/skills": "3".repeat(40) };
    const olderMarker = driftMarker(olderDrift);
    const closedOld = issue(3, { state: "closed", body: `old report\n\n${olderMarker}` });
    const openNew = issue(4, { body: `new report\n\n${marker}` });
    const resolved = issue(5, { state: "closed", body: resolvedBody("done") });

    const match = fakeGitHub([closedOld, openNew, resolved]);
    await notify(lock, "b".repeat(40), lock.trees, false, match.request, MAIN_ENV);
    const patches = writes(match.calls);
    expect(patches.map((call) => call.endpoint)).toEqual([
      `/repos/${REPOSITORY}/issues/3`,
      `/repos/${REPOSITORY}/issues/4`,
    ]);
    expect(must(patches[0]).body).not.toHaveProperty("state");
    expect(must(patches[1]).body).toMatchObject({ state: "closed" });
    for (const patch of patches) {
      expect(bodyText(patch)).toContain("<!-- omp-source-resolved -->");
      expect(bodyText(patch)).not.toContain("omp-source-current");
    }

    // Both issues now carry the state the baseline match wrote; the older drift recurs and must be reported.
    const afterMatch = [
      issue(3, { state: "closed", body: bodyText(must(patches[0])) }),
      issue(4, { state: "closed", body: bodyText(must(patches[1])) }),
      resolved,
    ];
    const recurrence = fakeGitHub(afterMatch);
    await notify(lock, "b".repeat(40), olderDrift, true, recurrence.request, MAIN_ENV);
    const refresh = must(writes(recurrence.calls)[0]);
    expect(refresh.endpoint).toBe(`/repos/${REPOSITORY}/issues/3`);
    expect(refresh.body).toMatchObject({ state: "open", assignees: ["clssck"] });
    expect(bodyText(refresh)).toContain(olderMarker);
  });

  test("resolving closes the open issue and records the resolved state in its body", async () => {
    const { calls, request } = fakeGitHub([issue(7, { body: `report\n\n${marker}` })]);
    await notify(lock, "b".repeat(40), lock.trees, false, request, MAIN_ENV);
    const patch = must(writes(calls)[0]);
    expect(patch.body).toMatchObject({ state: "closed" });
    expect(bodyText(patch)).toContain("<!-- omp-source-resolved -->");
    expect(bodyText(patch)).not.toContain("omp-source-current");
  });

  test("opens an issue when none exists on any page", async () => {
    const { calls, request } = fakeGitHub(filler(3, 1));
    await notify(lock, "b".repeat(40), drift, true, request, MAIN_ENV);
    const created = must(writes(calls)[0]);
    expect(created.method).toBe("POST");
    expect(created.endpoint).toBe(`/repos/${REPOSITORY}/issues`);
    expect(bodyText(created)).toContain(marker);
    expect(bodyText(created)).toContain(OWNERSHIP_MARKER);
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
    await notify(lock, "b".repeat(40), drift, true, request, MAIN_ENV);
    const [firstWrite, ...rest] = writes(calls);
    const created = must(firstWrite);
    expect(rest).toEqual([]);
    expect(created.method).toBe("POST");
    expect(created.endpoint).toBe(`/repos/${REPOSITORY}/issues`);
    expect(bodyText(created)).toContain(OWNERSHIP_MARKER);
  });

  test("a baseline match never closes or rewrites a foreign same-title issue", async () => {
    const { calls, request } = fakeGitHub([
      foreign(1, { body: `report\n\n${marker}` }),
      foreign(2, { state: "closed", body: `report\n\n${marker}` }),
      foreign(3, { body: `report\n\n${marker}`, user: { login: NOTIFICATION_AUTHOR } }),
    ]);
    await notify(lock, "b".repeat(40), lock.trees, false, request, MAIN_ENV);
    expect(writes(calls)).toEqual([]);
  });

  test("new drift refreshes the owned issue and leaves a foreign duplicate alone", async () => {
    const oldMarker = driftMarker({ ".omp/skills": "3".repeat(40) });
    const { calls, request } = fakeGitHub([
      foreign(1, { body: oldMarker }),
      issue(2, { state: "closed", body: oldMarker }),
    ]);
    await notify(lock, "b".repeat(40), drift, true, request, MAIN_ENV);
    const [firstWrite, secondWrite, ...rest] = writes(calls);
    const patch = must(firstWrite);
    const comment = must(secondWrite);
    expect(rest).toEqual([]);
    expect(patch.endpoint).toBe(`/repos/${REPOSITORY}/issues/2`);
    expect(patch.body).toMatchObject({ state: "open", assignees: ["clssck"] });
    expect(bodyText(patch)).toContain(marker);
    expect(bodyText(patch)).toContain(OWNERSHIP_MARKER);
    expect(comment.endpoint).toBe(`/repos/${REPOSITORY}/issues/2/comments`);
  });

  test("a baseline match closes only owned duplicates and keeps their ownership", async () => {
    const { calls, request } = fakeGitHub([
      foreign(1, { body: `report\n\n${marker}` }),
      issue(2, { body: `report\n\n${marker}` }),
      foreign(3, { body: `report\n\n${marker}` }),
      issue(4, { state: "closed", body: `report\n\n${marker}` }),
    ]);
    await notify(lock, "b".repeat(40), lock.trees, false, request, MAIN_ENV);
    const patches = writes(calls);
    expect(patches.map((call) => call.endpoint)).toEqual([
      `/repos/${REPOSITORY}/issues/2`,
      `/repos/${REPOSITORY}/issues/4`,
    ]);
    expect(must(patches[0]).body).toMatchObject({ state: "closed" });
    expect(must(patches[1]).body).not.toHaveProperty("state");
    for (const patch of patches) {
      expect(bodyText(patch)).toContain(OWNERSHIP_MARKER);
      expect(bodyText(patch)).toContain("<!-- omp-source-resolved -->");
    }
  });

  test("an unchanged owned report beside a foreign same-title issue writes nothing", async () => {
    const { calls, request } = fakeGitHub([foreign(1), issue(2, { body: marker })]);
    await notify(lock, "b".repeat(40), drift, true, request, MAIN_ENV);
    expect(writes(calls)).toEqual([]);
  });

  test("every issue body this automation writes is recognised as owned on the next run", async () => {
    const first = fakeGitHub([]);
    await notify(lock, "b".repeat(40), drift, true, first.request, MAIN_ENV);
    const created = bodyText(must(writes(first.calls)[0]));
    const second = fakeGitHub([
      {
        number: 5,
        title: TITLE,
        body: created,
        state: "open",
        user: { login: NOTIFICATION_AUTHOR },
      },
    ]);
    await notify(lock, "b".repeat(40), drift, true, second.request, MAIN_ENV);
    expect(writes(second.calls)).toEqual([]);
  });
});
