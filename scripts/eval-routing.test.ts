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
  parseArgs,
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

const BUDGET = 6;
const local = assistant(read("web/src/components/Header.tsx"));

const failed = (stopReason: string, ...content: unknown[]) => ({
  type: "message_end",
  message: { role: "assistant", content, stopReason, errorMessage: "upstream overloaded" },
});

function track(events: unknown[], maxMessages = BUDGET): RoutingTracker {
  const tracker = new RoutingTracker(new Set(["animate", "dbt", "break-ui"]), maxMessages);
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
    const early = track([local, local, assistant(read("skill://break-ui"))]);
    expect(early.skills).toEqual(["break-ui"]);
    expect(early.capped).toBe(false);
  });

  test("a run still exploring at the budget is capped, not a no-skill answer", () => {
    const exploring = track([
      ...Array.from({ length: BUDGET }, () => local),
      assistant(read("skill://break-ui")),
    ]);
    expect([exploring.done, exploring.capped, exploring.messages]).toEqual([true, true, BUDGET]);
    expect(exploring.skills).toEqual([]);
    const answered = track([local, local, assistant(text)]);
    expect([answered.done, answered.capped, answered.messages]).toEqual([true, false, 3]);
    expect(answered.skills).toEqual([]);
  });

  test("a skill read or a final answer on the last budgeted message is a decision, not a cap", () => {
    const explore = Array.from({ length: BUDGET - 1 }, () => local);
    const skillRead = track([...explore, assistant(read("skill://break-ui"))]);
    expect([skillRead.capped, skillRead.messages, skillRead.skills]).toEqual([
      false,
      BUDGET,
      ["break-ui"],
    ]);
    const answered = track([...explore, assistant(text)]);
    expect([answered.capped, answered.messages, answered.skills]).toEqual([false, BUDGET, []]);
  });

  test("a longer budget lets a late skill read through; a run that ends first is not capped", () => {
    const late = [...Array.from({ length: BUDGET }, () => local), assistant(read("skill://dbt"))];
    const longer = track(late, BUDGET + 2);
    expect([longer.capped, longer.messages, longer.skills]).toEqual([false, BUDGET + 1, ["dbt"]]);
    const ended = track([local, { type: "agent_end" }]);
    expect([ended.done, ended.capped, ended.skills]).toEqual([true, false, []]);
    expect(ended.error).toBeDefined();
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

  test("agent_end before a decision is an error, never a no-skill answer; malformed events are ignored", () => {
    const tracker = track([null, "x", { type: "message_end" }, { type: "agent_end" }]);
    expect(tracker.done).toBe(true);
    expect(tracker.messages).toBe(0);
    expect(tracker.skills).toEqual([]);
    expect(tracker.capped).toBe(false);
    expect(tracker.error).toContain("agent_end");
  });

  test("a decided run is not turned into an error by the agent_end that follows", () => {
    const answered = track([assistant(text), { type: "agent_end" }]);
    expect([answered.done, answered.error, answered.skills]).toEqual([true, undefined, []]);
    const routed = track([assistant(read("skill://animate")), { type: "agent_end" }]);
    expect([routed.done, routed.error, routed.skills]).toEqual([true, undefined, ["animate"]]);
  });

  for (const stopReason of ["error", "aborted"]) {
    test(`an assistant message that ends ${stopReason} with no content is an error, not a no-skill answer`, () => {
      const tracker = track([failed(stopReason)]);
      expect([tracker.done, tracker.capped, tracker.skills, tracker.messages]).toEqual([
        true,
        false,
        [],
        1,
      ]);
      expect(tracker.error).toContain(stopReason);
      expect(tracker.error).toContain("upstream overloaded");
    });

    test(`a partial skill call on a message that ends ${stopReason} is not a route`, () => {
      const tracker = track([
        failed(stopReason, read("skill://animate"), {
          type: "toolCall",
          name: "skill://<dbt>",
          arguments: {},
        }),
        assistant(read("skill://break-ui")),
      ]);
      expect([tracker.done, tracker.skills, tracker.malformed]).toEqual([true, [], []]);
      expect(tracker.error).toContain(stopReason);
    });

    test(`${stopReason} after exploring ends the run as an error, even on the last budgeted message`, () => {
      const tracker = track([
        ...Array.from({ length: BUDGET - 1 }, () => local),
        failed(stopReason),
      ]);
      expect([tracker.done, tracker.capped, tracker.skills]).toEqual([true, false, []]);
      expect(tracker.error).toContain(stopReason);
    });
  }

  test("a skill read in the first message stays a route; a later failed message is ignored", () => {
    const tracker = track([assistant(read("skill://animate")), failed("error")]);
    expect([tracker.skills, tracker.error]).toEqual([["animate"], undefined]);
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
    expect(scoreCase({ prompt: "p", expect: "dbt" }, ["dbt"], false)).toBe("clean");
    expect(scoreCase({ prompt: "p", expect: "dbt" }, ["atl", "dbt"], false)).toBe("extra");
    expect(scoreCase({ prompt: "p", expect: "dbt" }, ["atl"], false)).toBe("fail");
    expect(scoreCase({ prompt: "p", expect: null }, [], false)).toBe("clean");
    expect(scoreCase({ prompt: "p", expect: null }, ["atl"], false)).toBe("fail");
  });

  test("a capped run fails, including a null case that read no skill", () => {
    expect(scoreCase({ prompt: "p", expect: null }, [], true)).toBe("fail");
    expect(scoreCase({ prompt: "p", expect: "dbt" }, [], true)).toBe("fail");
  });
});

const run = (prompt: string, outcome: CaseResult["outcome"], capped = false): CaseResult => ({
  prompt,
  expect: "dbt",
  run: 0,
  skills: [],
  malformed: [],
  messages: capped ? BUDGET : 1,
  capped,
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

  test("capped runs count as failures toward the majority", () => {
    const [a, b] = summarizeCases(
      [
        { prompt: "a", expect: "dbt" },
        { prompt: "b", expect: "dbt" },
      ],
      [
        run("a", "clean"),
        run("a", "fail", true),
        run("a", "fail", true),
        run("b", "clean"),
        run("b", "clean"),
        run("b", "fail", true),
      ],
    );
    expect([a?.pass, a?.rate]).toEqual([false, 1 / 3]);
    expect([b?.pass, b?.rate]).toEqual([true, 2 / 3]);
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

  test("--cases resolves a relative file path and rejects a missing value", () => {
    expect(parseArgs(["--check", "--cases", "holdout.json"]).cases).toBe(
      path.resolve("holdout.json"),
    );
    expect(() => parseArgs(["--cases"])).toThrow("--cases needs a value");
  });

  test("--thinking defaults to off, accepts host levels, and rejects anything else", () => {
    expect(parseArgs([]).thinking).toBe("off");
    expect(parseArgs(["--thinking", "xhigh"]).thinking).toBe("xhigh");
    expect(parseArgs(["--thinking", "auto"]).thinking).toBe("auto");
    expect(() => parseArgs(["--thinking", "extreme"])).toThrow("--thinking must be one of");
    expect(() => parseArgs(["--thinking"])).toThrow("--thinking needs a value");
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
