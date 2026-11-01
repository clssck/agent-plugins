#!/usr/bin/env bun
// Skill routing eval: `bun scripts/eval-routing.ts [--check] [--cases PATH] [--only a,b] [--runs N] [--concurrency N] [--max-messages N] [--model M] [--thinking LEVEL] [--json PATH]`.
// Each case in the cases file (default evals/routing.json; --cases PATH selects another, e.g. a frozen holdout) is sent to the real host (`omp -p --mode json --no-session --tools read
// --thinking LEVEL`) from a copy of evals/fixtures/workspace. The first skill-read attempt is the routing
// decision; it does not prove successful loading or use of the body. Nothing but `read` can execute.
// A run still undecided after --max-messages assistant messages (default 12) is reported as capped:
// censored by the budget, scored as a failure, and kept apart from completed no-skill answers.
// It measures the installed environment: the packs as `omp plugin list` links them, plus any other installed
// skills and the user's settings. The model defaults to anthropic/claude-haiku-5-5; --model default uses the
// user's configured model. --thinking defaults to off; the host maps each level to what the model supports, so
// "off" is not disabled reasoning on every model. Cases whose skill the host's `disabledExtensions`
// setting turns off are reported as SKIP, not run. Results are model evidence, not a gate. `--check` validates
// the cases against packs/*/skills without calling a model.

import { cp, mkdtemp, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { frontmatter, isRecord } from "./sync";

const ROOT = path.resolve(import.meta.dir, "..");
export const CASES_FILE = path.join(ROOT, "evals/routing.json");
/** Sample project every case runs in, so requests about files find files instead of stopping to ask. */
const WORKSPACE = path.join(ROOT, "evals/fixtures/workspace");
/** Default assistant-message budget for a skill read; covers looking at the files first, then reading the skill. */
const DEFAULT_MAX_MESSAGES = 12;
const TIMEOUT_MS = 120_000;

export interface RoutingCase {
  prompt: string;
  /** Skill the agent should read first; null when no skill should be read. */
  expect: string | null;
}

/** Model-invocable skill names across packs/*\/skills (not disabled, hidden, or manual-only). */
export async function routableSkills(packsDir = path.join(ROOT, "packs")): Promise<Set<string>> {
  const names = new Set<string>();
  for (const pack of await readdir(packsDir, { withFileTypes: true })) {
    if (!pack.isDirectory()) {
      continue;
    }
    const skillsDir = path.join(packsDir, pack.name, "skills");
    const entries = await readdir(skillsDir, { withFileTypes: true }).catch(() => []);
    for (const entry of entries) {
      const file = Bun.file(path.join(skillsDir, entry.name, "SKILL.md"));
      if (!entry.isDirectory() || !(await file.exists())) {
        continue;
      }
      const meta = frontmatter(await file.text());
      if (
        !meta ||
        meta.enabled === false ||
        meta.hide === true ||
        meta["disable-model-invocation"] === true
      ) {
        continue;
      }
      names.add(typeof meta.name === "string" ? meta.name : entry.name);
    }
  }
  return names;
}

/** Parse the cases file; throws on a shape the runner cannot use. */
export function parseCases(text: string): RoutingCase[] {
  const data: unknown = JSON.parse(text);
  if (!isRecord(data) || !Array.isArray(data.cases)) {
    throw new Error("cases file must be an object with a `cases` array");
  }
  return data.cases.map((item: unknown, index) => {
    const prompt = isRecord(item) ? item.prompt : undefined;
    const expected = isRecord(item) ? item.expect : undefined;
    if (typeof prompt !== "string" || !(typeof expected === "string" || expected === null)) {
      throw new Error(`case ${index}: needs a string prompt and a string or null expect`);
    }
    return { prompt, expect: expected };
  });
}

/** Problems that make the case set unusable or stale; empty when it is valid. */
export function caseProblems(cases: RoutingCase[], skills: Set<string>): string[] {
  const problems: string[] = [];
  const seen = new Set<string>();
  cases.forEach(({ prompt, expect }, index) => {
    const at = `case ${index} (${JSON.stringify(prompt.slice(0, 40))})`;
    if (!prompt.trim()) {
      problems.push(`${at}: empty prompt`);
    }
    // omp reads a leading @ as a file attachment and a leading - as a flag.
    if (/^[@-]/.test(prompt)) {
      problems.push(`${at}: prompt must not start with @ or -`);
    }
    if (seen.has(prompt)) {
      problems.push(`${at}: duplicate prompt`);
    }
    seen.add(prompt);
    if (expect !== null && !skills.has(expect)) {
      problems.push(`${at}: expects ${expect}, which is not a model-invocable pack skill`);
    }
  });
  const covered = new Set(cases.map((item) => item.expect));
  for (const skill of [...skills].toSorted()) {
    if (!covered.has(skill)) {
      problems.push(`${skill}: no case expects this skill`);
    }
  }
  if (!covered.has(null)) {
    problems.push("no case expects null (a request no skill should take)");
  }
  return problems;
}

/** Skill names in the host's `disabledExtensions` setting (`omp config get disabledExtensions --json`). */
export function disabledSkills(config: unknown): Set<string> {
  const value = isRecord(config) ? config.value : undefined;
  const names = (Array.isArray(value) ? value : [])
    .filter((entry): entry is string => typeof entry === "string" && entry.startsWith("skill:"))
    .map((entry) => entry.slice("skill:".length));
  return new Set(names);
}

/** Skill name a `read` path addresses, or undefined when it is not a skill:// path. */
export function skillOfPath(target: unknown): string | undefined {
  if (typeof target !== "string" || !target.startsWith("skill://")) {
    return undefined;
  }
  const name = target.slice("skill://".length).split(/[/:?#]/, 1)[0];
  return name === "" ? undefined : name;
}

/**
 * Routing decision from the host's JSON event stream. `push` returns true once the run is over: the first
 * assistant message that reads a skill, the first one with no tool call (it answered), a failed assistant
 * message, `agent_end`, or the `maxMessages`-th assistant message still without a decision. Only that last
 * case sets `capped`: the budget censored the run, so it is not a no-skill answer. A skill read or an answer
 * on the last budgeted message is a decision, not a cap.
 * An assistant message that ends with stopReason `error` or `aborted` is not an answer, and its tool calls (a
 * partial stream) are not routes: the run ends with `error` set. `agent_end` before any decision likewise
 * sets `error`; the host emits it on its own failures, so it is never a completed no-skill answer.
 * A call whose tool name is itself a skill:// URL naming a known skill is a malformed attempt on that skill: it
 * counts as the route, and `malformed` records it, because the host rejects the call and the skill never loads.
 * Unknown names (a placeholder such as `skill://<name>`) are ignored.
 */
export class RoutingTracker {
  skills: string[] = [];
  malformed: string[] = [];
  messages = 0;
  capped = false;
  done = false;
  /** Why the run ended without a usable decision (failed assistant message, or agent_end with none). */
  error: string | undefined;

  constructor(
    private readonly known: ReadonlySet<string>,
    private readonly maxMessages: number,
  ) {}

  push(event: unknown): boolean {
    if (this.done) {
      return true;
    }
    if (!isRecord(event)) {
      return false;
    }
    if (event.type === "agent_end") {
      this.error = "agent_end before a completed assistant decision";
      this.done = true;
      return true;
    }
    const message = event.message;
    if (event.type !== "message_end" || !isRecord(message) || message.role !== "assistant") {
      return false;
    }
    this.messages += 1;
    if (message.stopReason === "error" || message.stopReason === "aborted") {
      const detail =
        typeof message.errorMessage === "string" && message.errorMessage
          ? `: ${message.errorMessage}`
          : "";
      this.error = `assistant message ended with stopReason ${message.stopReason}${detail}`;
      this.done = true;
      return true;
    }
    const calls = (Array.isArray(message.content) ? message.content : []).filter(
      (part: unknown): part is Record<string, unknown> =>
        isRecord(part) && part.type === "toolCall",
    );
    for (const call of calls) {
      const name = typeof call.name === "string" ? call.name : "";
      const guessed = skillOfPath(name.replaceAll(/[<>]/g, ""));
      const attempted = guessed && this.known.has(guessed) ? guessed : undefined;
      const skill =
        attempted ??
        (name === "read" && isRecord(call.arguments)
          ? skillOfPath(call.arguments.path)
          : undefined);
      if (skill && !this.skills.includes(skill)) {
        this.skills.push(skill);
      }
      if (attempted && !this.malformed.includes(attempted)) {
        this.malformed.push(attempted);
      }
    }
    const decided = this.skills.length > 0 || calls.length === 0;
    this.capped = !decided && this.messages >= this.maxMessages;
    this.done = decided || this.capped;
    return this.done;
  }
}

export interface CaseResult extends RoutingCase {
  run: number;
  skills: string[];
  /** Skills the agent tried to open with a malformed call (tool name `skill://...`). */
  malformed: string[];
  /** Assistant messages seen before the run ended. */
  messages: number;
  /** The message budget ran out with no decision; scored as a failure. */
  capped: boolean;
  outcome: Outcome;
  error?: string;
}

/** `clean`: exactly the expected skill (or none) was read. `extra`: the expected skill plus others. */
export type Outcome = "clean" | "extra" | "fail";

/** Majority of a case's runs must pass, as in Anthropic's skill-creator trigger eval (threshold 0.5). */
const CASE_THRESHOLD = 0.5;

export interface CaseSummary extends RoutingCase {
  runs: CaseResult[];
  /** Fraction of runs that read the expected skill (or none, for a null case). */
  rate: number;
  pass: boolean;
  /** At least one passing run also read another skill. */
  extra: boolean;
}

/** Group runs by case, in case order; a case passes when more than CASE_THRESHOLD of its runs pass. */
export function summarizeCases(cases: RoutingCase[], results: CaseResult[]): CaseSummary[] {
  return cases.flatMap((item) => {
    const runs = results.filter((result) => result.prompt === item.prompt);
    if (runs.length === 0) {
      return [];
    }
    const rate = runs.filter((run) => run.outcome !== "fail").length / runs.length;
    const extra = runs.some((run) => run.outcome === "extra");
    return [{ ...item, runs, rate, pass: rate > CASE_THRESHOLD, extra }];
  });
}

/** A capped run made no decision within the message budget, so it fails whatever the case expects. */
export function scoreCase(item: RoutingCase, skills: string[], capped: boolean): Outcome {
  if (capped) {
    return "fail";
  }
  if (item.expect === null) {
    return skills.length === 0 ? "clean" : "fail";
  }
  if (!skills.includes(item.expect)) {
    return "fail";
  }
  return skills.length === 1 ? "clean" : "extra";
}

async function runCase(
  item: RoutingCase,
  run: number,
  cwd: string,
  model: string | undefined,
  thinking: string,
  known: ReadonlySet<string>,
  maxMessages: number,
): Promise<CaseResult> {
  const argv = [
    "omp",
    "-p",
    "--mode",
    "json",
    "--no-session",
    "--tools",
    "read",
    "--thinking",
    thinking,
    "--cwd",
    cwd,
  ];
  if (model) {
    argv.push("--model", model);
  }
  argv.push(item.prompt);
  const proc = Bun.spawn(argv, { cwd, stdout: "pipe", stderr: "pipe", stdin: "ignore" });
  const stderr = new Response(proc.stderr).text();
  const tracker = new RoutingTracker(known, maxMessages);
  const timer = setTimeout(() => proc.kill(), TIMEOUT_MS);
  let error: string | undefined;
  try {
    const decoder = new TextDecoder();
    let buffer = "";
    read: for await (const chunk of proc.stdout) {
      buffer += decoder.decode(chunk, { stream: true });
      let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        newline = buffer.indexOf("\n");
        if (!line.startsWith("{")) {
          continue;
        }
        let event: unknown;
        try {
          event = JSON.parse(line);
        } catch {
          continue;
        }
        if (tracker.push(event)) {
          break read;
        }
      }
    }
  } finally {
    clearTimeout(timer);
    proc.kill();
    await proc.exited;
  }
  error = tracker.error;
  if (!tracker.done) {
    const tail = (await stderr).trim().split("\n").slice(-3).join(" | ");
    error = `no decision after ${tracker.messages} message(s), exit ${proc.signalCode ?? proc.exitCode}: ${tail}`;
  }
  const { skills, malformed, messages, capped } = tracker;
  return error
    ? { ...item, run, skills, malformed, messages, capped, outcome: "fail", error }
    : {
        ...item,
        run,
        skills,
        malformed,
        messages,
        capped,
        outcome: scoreCase(item, skills, capped),
      };
}

async function pool<T, R>(items: T[], limit: number, work: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = Array.from({ length: items.length });
  // One shared iterator: each worker takes the next unclaimed item.
  const queue = items.entries();
  const worker = async () => {
    for (const [index, item] of queue) {
      results[index] = await work(item);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

/** Benchmark model: inexpensive enough to repeat every case. */
export const DEFAULT_MODEL = "anthropic/claude-haiku-5-5";
/** Levels `omp --thinking` accepts. */
export const THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "max", "auto"];

export interface Options {
  check: boolean;
  only?: Set<string>;
  runs: number;
  concurrency: number;
  /** Assistant messages a run may take before it is capped. */
  maxMessages: number;
  /** undefined: the user's configured omp model. */
  model: string | undefined;
  /** Requested `omp --thinking` level; default off. */
  thinking: string;
  json?: string;
  /** Cases file; the shipped evals/routing.json unless --cases names another. */
  cases: string;
}

const USAGE =
  "usage: bun scripts/eval-routing.ts [--check] [--cases PATH] [--only skill,none,...] [--runs N] [--concurrency N] [--max-messages N] [--model M|default] [--thinking LEVEL] [--json PATH]\n";

export function parseArgs(argv: string[]): Options {
  const options: Options = {
    check: false,
    runs: 3,
    concurrency: 8,
    maxMessages: DEFAULT_MAX_MESSAGES,
    model: DEFAULT_MODEL,
    thinking: "off",
    cases: CASES_FILE,
  };
  for (let index = 0; index < argv.length; index++) {
    const flag = argv[index] ?? "";
    const value = () => {
      const next = argv[++index];
      if (next === undefined) {
        throw new Error(`${flag} needs a value`);
      }
      return next;
    };
    const count = () => {
      const number = Number(value());
      if (!Number.isInteger(number) || number < 1) {
        throw new Error(`${flag} needs a positive integer`);
      }
      return number;
    };
    switch (flag) {
      case "--check":
        options.check = true;
        break;
      case "--only":
        options.only = new Set(value().split(","));
        break;
      case "--runs":
        options.runs = count();
        break;
      case "--concurrency":
        options.concurrency = count();
        break;
      case "--max-messages":
        options.maxMessages = count();
        break;
      case "--model": {
        const model = value();
        options.model = model === "default" ? undefined : model;
        break;
      }
      case "--thinking": {
        const thinking = value();
        if (!THINKING_LEVELS.includes(thinking)) {
          throw new Error(`--thinking must be one of ${THINKING_LEVELS.join(", ")}`);
        }
        options.thinking = thinking;
        break;
      }
      case "--json":
        options.json = value();
        break;
      case "--cases":
        options.cases = path.resolve(value());
        break;
      default:
        throw new Error(`unknown argument ${flag}`);
    }
  }
  return options;
}

if (import.meta.main) {
  let options: Options;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n${USAGE}`);
    process.exit(2);
  }
  const cases = parseCases(await Bun.file(options.cases).text());
  const known = await routableSkills();
  const problems = caseProblems(cases, known);
  if (problems.length > 0) {
    process.stderr.write(`${problems.length} case problem(s) in ${options.cases}:\n`);
    for (const problem of problems) {
      process.stderr.write(`  - ${problem}\n`);
    }
    process.exit(2);
  }
  const selected = cases.filter((item) => !options.only || options.only.has(item.expect ?? "none"));
  if (options.check) {
    process.stdout.write(`${cases.length} routing cases valid (${options.cases})\n`);
    process.exit(0);
  }
  if (selected.length === 0) {
    process.stderr.write("--only matched no cases\n");
    process.exit(2);
  }

  const scratch = await mkdtemp(path.join(tmpdir(), "eval-routing-"));
  let results: CaseResult[];
  let skipped: RoutingCase[];
  try {
    // Read-only runs cannot change the copy, so every case shares it.
    await cp(WORKSPACE, scratch, { recursive: true });
    // Ask the host, from the same cwd the cases run in, which skills it will not offer.
    const config = Bun.spawnSync(["omp", "config", "get", "disabledExtensions", "--json"], {
      cwd: scratch,
    });
    const disabled = disabledSkills(
      config.exitCode === 0 ? JSON.parse(config.stdout.toString()) : undefined,
    );
    skipped = selected.filter((item) => item.expect !== null && disabled.has(item.expect));
    for (const item of skipped) {
      process.stdout.write(
        `SKIP  ${item.expect} is disabled in omp config  ${JSON.stringify(item.prompt)}\n`,
      );
    }
    const jobs = selected
      .filter((item) => !skipped.includes(item))
      .flatMap((item) => Array.from({ length: options.runs }, (_, run) => ({ item, run })));
    let finished = 0;
    results = await pool(jobs, options.concurrency, async ({ item, run }) => {
      const result = await runCase(
        item,
        run,
        scratch,
        options.model,
        options.thinking,
        known,
        options.maxMessages,
      );
      finished += 1;
      process.stderr.write(`\r${finished}/${jobs.length} runs`);
      return result;
    });
    process.stderr.write("\n");
  } finally {
    await rm(scratch, { recursive: true, force: true });
  }

  const summaries = summarizeCases(selected, results);
  const describe = (run: CaseResult) =>
    run.error ??
    (run.capped
      ? `capped after ${run.messages} messages`
      : run.skills
          .map((skill) => (run.malformed.includes(skill) ? `${skill} (malformed call)` : skill))
          .join("+") || "none");
  for (const summary of summaries.toSorted((a, b) => a.rate - b.rate)) {
    const label = summary.pass ? (summary.extra ? "PASS+" : "PASS ") : "FAIL ";
    const passed = summary.runs.filter((run) => run.outcome !== "fail").length;
    const got = summary.runs.every((run) => run.outcome === "clean")
      ? ""
      : ` <- ${summary.runs.map(describe).join(", ")}`;
    process.stdout.write(
      `${label} ${passed}/${summary.runs.length}  ${summary.expect ?? "none"}${got}  ${JSON.stringify(summary.prompt)}\n`,
    );
  }

  // Per expected skill: the share of its runs that read it (none, for null cases). A low row is where to look,
  // not proof of a bad description: misroutes, skipped skills, and capped runs all lower it (see the totals).
  const bySkill = new Map<string, { ok: number; total: number }>();
  for (const result of results) {
    const key = result.expect ?? "none";
    const row = bySkill.get(key) ?? { ok: 0, total: 0 };
    row.total += 1;
    row.ok += result.outcome === "fail" ? 0 : 1;
    bySkill.set(key, row);
  }
  process.stdout.write("\nper skill (runs that read the expected skill):\n");
  for (const [skill, { ok, total }] of [...bySkill].toSorted(
    ([, a], [, b]) => a.ok / a.total - b.ok / b.total,
  )) {
    const percent = String(Math.round((ok / total) * 100)).padStart(3);
    process.stdout.write(`  ${percent}%  ${ok}/${total}  ${skill}\n`);
  }

  const count = (outcome: Outcome) => results.filter((row) => row.outcome === outcome).length;
  const failed = results.filter((result) => result.outcome === "fail");
  const errors = failed.filter((result) => result.error).length;
  // A failed run either read the wrong skill (misrouted), answered without reading one (skipped skills), hit the
  // message budget undecided (capped: censored, not an answer), or never reached a decision (error).
  const misrouted = failed.filter((result) => !result.error && result.skills.length > 0).length;
  const capped = failed.filter((result) => result.capped).length;
  const passedCases = summaries.filter((summary) => summary.pass).length;
  process.stdout.write(
    `\nmodel ${options.model ?? "default"}, thinking ${options.thinking}, max ${options.maxMessages} messages, ${options.runs} run(s) per case: ${passedCases}/${summaries.length} cases passed\n` +
      `runs: ${count("clean")} clean, ${count("extra")} with extra skill reads, ${misrouted} misrouted ` +
      `(includes no-skill cases that read one), ${failed.length - misrouted - capped - errors} completed without reading a skill, ` +
      `${capped} capped after ${options.maxMessages} messages (no decision; counted as failures)` +
      (errors ? `, ${errors} without a decision` : "") +
      (skipped.length ? `; ${skipped.length} case(s) skipped (skill disabled)` : "") +
      `; ${results.filter((result) => result.malformed.length > 0).length} with a malformed skill call\n`,
  );
  if (options.json) {
    await Bun.write(
      options.json,
      `${JSON.stringify({ casesFile: options.cases, model: options.model ?? "default", thinking: options.thinking, maxMessages: options.maxMessages, runs: options.runs, skipped, cases: summaries }, null, 2)}\n`,
    );
  }
  process.exit(passedCases === summaries.length ? 0 : 1);
}
