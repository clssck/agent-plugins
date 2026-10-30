import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";
import {
  CASES_FILE,
  type CaseResult,
  RoutingTracker,
  caseProblems,
  disabledSkills,
  parseCases,
  routableSkills,
  scoreCase,
  skillOfPath,
  summarizeCases,
} from "./eval-routing";

const assistant = (...content: unknown[]) => ({
  type: "message_end",
  message: { role: "assistant", content },
});
const read = (target: string) => ({ type: "toolCall", name: "read", arguments: { path: target } });
const text = { type: "text", text: "answer" };

function track(events: unknown[]): RoutingTracker {
  const tracker = new RoutingTracker(new Set(["animate", "dbt", "break-ui"]));
  for (const event of events) {
    if (tracker.push(event)) {
      break;
    }
  }
  return tracker;
}

describe("RoutingTracker", () => {
  test("the first assistant message that reads a skill decides the route", () => {
    const tracker = track([
      { type: "message_end", message: { role: "user", content: [text] } },
      assistant({ type: "thinking" }, read("skill://animation-vocabulary")),
      assistant(read("skill://animate")),
    ]);
    expect(tracker.done).toBe(true);
    expect(tracker.skills).toEqual(["animation-vocabulary"]);
  });

  test("parallel skill reads in one message are all kept, once each", () => {
    const tracker = track([
      assistant(
        read("skill://dbt/references/ci.md"),
        read("skill://dbt"),
        read("skill://atl:1-20"),
      ),
    ]);
    expect(tracker.skills).toEqual(["dbt", "atl"]);
  });

  test("an answer with no tool call ends the run with no skill", () => {
    const tracker = track([assistant(text), assistant(read("skill://animate"))]);
    expect(tracker.done).toBe(true);
    expect(tracker.skills).toEqual([]);
  });

  test("non-skill reads keep watching until a skill read or the message cap", () => {
    const local = assistant(read("web/src/components/Header.tsx"));
    expect(track([local, local, assistant(read("skill://break-ui"))]).skills).toEqual(["break-ui"]);
    const capped = track([
      ...Array.from({ length: 6 }, () => local),
      assistant(read("skill://break-ui")),
    ]);
    expect(capped.done).toBe(true);
    expect(capped.skills).toEqual([]);
  });

  test("a skill:// URL used as the tool name is a malformed attempt on that skill", () => {
    const tracker = track([
      assistant(read("."), { type: "toolCall", name: "skill://<animate>", arguments: {} }),
    ]);
    expect(tracker.skills).toEqual(["animate"]);
    expect(tracker.malformed).toEqual(["animate"]);
    expect(track([assistant(read("skill://animate"))]).malformed).toEqual([]);
  });

  test("a malformed call naming no known skill (a placeholder) is not a route", () => {
    const tracker = track([
      assistant({ type: "toolCall", name: "skill://<name>", arguments: {} }),
      assistant(text),
    ]);
    expect(tracker.skills).toEqual([]);
    expect(tracker.malformed).toEqual([]);
  });

  test("agent_end without a decision still finishes; malformed events are ignored", () => {
    const tracker = track([null, "x", { type: "message_end" }, { type: "agent_end" }]);
    expect(tracker.done).toBe(true);
    expect(tracker.messages).toBe(0);
  });
});

describe("skillOfPath", () => {
  test("takes the skill root from skill:// paths only", () => {
    expect(skillOfPath("skill://remove-animations")).toBe("remove-animations");
    expect(skillOfPath("skill://atl/references/editing.md#top")).toBe("atl");
    expect(skillOfPath("/Users/x/packs/clssck/skills/animate/SKILL.md")).toBeUndefined();
    expect(skillOfPath("skill://")).toBeUndefined();
  });
});

describe("scoreCase", () => {
  test("only the expected skill is clean; extra reads are flagged; a miss or any read on a null case fails", () => {
    expect(scoreCase({ prompt: "p", expect: "dbt" }, ["dbt"])).toBe("clean");
    expect(scoreCase({ prompt: "p", expect: "dbt" }, ["atl", "dbt"])).toBe("extra");
    expect(scoreCase({ prompt: "p", expect: "dbt" }, ["atl"])).toBe("fail");
    expect(scoreCase({ prompt: "p", expect: null }, [])).toBe("clean");
    expect(scoreCase({ prompt: "p", expect: null }, ["atl"])).toBe("fail");
  });
});

const run = (prompt: string, outcome: CaseResult["outcome"]): CaseResult => ({
  prompt,
  expect: "dbt",
  run: 0,
  skills: [],
  malformed: [],
  outcome,
});

describe("summarizeCases", () => {
  test("a case passes only when more than half its runs pass; extra reads still count as passes", () => {
    const cases = [
      { prompt: "a", expect: "dbt" },
      { prompt: "b", expect: "dbt" },
      { prompt: "c", expect: "dbt" },
    ];
    const [a, b, c] = summarizeCases(cases, [
      run("a", "clean"),
      run("a", "extra"),
      run("a", "fail"),
      run("b", "clean"),
      run("b", "fail"),
      run("c", "fail"),
    ]);
    expect([a?.pass, a?.extra, a?.rate]).toEqual([true, true, 2 / 3]);
    expect([b?.pass, b?.rate]).toEqual([false, 0.5]);
    expect([c?.pass, c?.rate]).toEqual([false, 0]);
  });

  test("cases with no runs (skipped) are left out", () => {
    expect(summarizeCases([{ prompt: "x", expect: "dbt" }], [])).toEqual([]);
  });
});

describe("disabledSkills", () => {
  test("keeps only skill: entries from the host's disabledExtensions value", () => {
    const config = {
      key: "disabledExtensions",
      value: ["mcp:exa", "skill:write-swift", "slash-command:release", "skill:mobile-native", 3],
    };
    expect([...disabledSkills(config)]).toEqual(["write-swift", "mobile-native"]);
    expect(disabledSkills({ key: "disabledExtensions" }).size).toBe(0);
  });
});

describe("cases", () => {
  let root: string;
  beforeEach(async () => {
    root = await mkdtemp(path.join(tmpdir(), "eval-routing-"));
  });
  afterEach(() => rm(root, { recursive: true, force: true }));

  async function skill(pack: string, name: string, extra = "") {
    const dir = path.join(root, pack, "skills", name);
    await mkdir(dir, { recursive: true });
    await writeFile(
      path.join(dir, "SKILL.md"),
      `---\nname: ${name}\ndescription: Demo.\n${extra}---\n\n# Demo\n`,
    );
  }

  test("manual-only, hidden, and disabled skills are not routable", async () => {
    await skill("a", "visible");
    await skill("a", "manual", "disable-model-invocation: true\n");
    await skill("b", "hidden", "hide: true\n");
    await skill("b", "off", "enabled: false\n");
    expect([...(await routableSkills(root))]).toEqual(["visible"]);
  });

  test("stale, duplicate, unsafe, and uncovered cases are reported", () => {
    const problems = caseProblems(
      [
        { prompt: "fix my dbt model", expect: "dbt" },
        { prompt: "fix my dbt model", expect: "dbt" },
        { prompt: "@notes.md summarize", expect: null },
        { prompt: "write an ADR", expect: "adr" },
      ],
      new Set(["dbt", "atl"]),
    );
    expect(problems).toEqual([
      'case 1 ("fix my dbt model"): duplicate prompt',
      'case 2 ("@notes.md summarize"): prompt must not start with @ or -',
      'case 3 ("write an ADR"): expects adr, which is not a model-invocable pack skill',
      "atl: no case expects this skill",
    ]);
    expect(caseProblems([{ prompt: "x", expect: "dbt" }], new Set(["dbt"]))).toEqual([
      "no case expects null (a request no skill should take)",
    ]);
  });

  test("parseCases rejects a case without a string or null expect", () => {
    expect(() => parseCases('{"cases":[{"prompt":"x"}]}')).toThrow("case 0");
    expect(() => parseCases("[]")).toThrow("`cases` array");
  });

  test("the shipped cases cover every routable pack skill and name only real ones", async () => {
    const cases = parseCases(await Bun.file(CASES_FILE).text());
    expect(caseProblems(cases, await routableSkills())).toEqual([]);
  });
});
