import { describe, expect, test } from "bun:test";
import { headingSlug, maskFences, maskNonPayload, payloadProblems } from "./payload-grammar";

const SKILL = `# Title

One paragraph.

<critical>
- NEVER ship unverified work.
</critical>

<instruction>
Use X when available; else Y.
</instruction>

<procedure>
1. Do the work.
2. Verify the result.
</procedure>

<caution>
Blocked -> report the prerequisite.
</caution>
`;

describe("headingSlug", () => {
	test("matches GitHub anchors for headings used in skill links", () => {
		expect(headingSlug("Payload grammar")).toBe("payload-grammar");
		expect(headingSlug("dbt `data_type`")).toBe("dbt-data_type");
		expect(headingSlug("8. Environment-Scoped Secrets vs `secrets: inherit`")).toBe(
			"8-environment-scoped-secrets-vs-secrets-inherit",
		);
		expect(headingSlug("SEV3 — Moderate")).toBe("sev3--moderate");
	});
});

describe("maskFences", () => {
	test("keeps inline code so heading slugs stay exact", () => {
		expect(maskFences("## 12. Cache Poisoning and `cache-mode`")).toBe("## 12. Cache Poisoning and `cache-mode`");
	});
});

describe("maskNonPayload", () => {
	test("blanks frontmatter, fences, and inline code while keeping line numbers", () => {
		const text = ["---", "description: '<critical>'", "---", "", "```md", "<procedure>", "```", "`<caution>`"].join("\n");
		const masked = maskNonPayload(text);
		expect(masked.split("\n")).toHaveLength(8);
		expect(masked).not.toContain("<critical>");
		expect(masked).not.toContain("<procedure>");
		expect(masked).not.toContain("<caution>");
	});
});

describe("payloadProblems", () => {
	test("accepts an ordered, closed payload", () => {
		expect(payloadProblems("skill", SKILL)).toEqual([]);
	});

	test("accepts a skill that has not converted yet", () => {
		expect(payloadProblems("skill", "# Title\n\nProse only.\n")).toEqual([]);
	});

	test("reports an unclosed tag", () => {
		const problems = payloadProblems("skill", "<critical>\n- NEVER.\n");
		expect(problems.map(problem => problem.message)).toContain("<critical> is never closed");
	});

	test("allows host-style section tags, attributes, and nesting", () => {
		const body = "<directives>\n- MUST do it.\n- SHOULD prefer it.\n</directives>\n\n<example name=\"finding\">\n<title>Short title</title>\n<body>Bug, trigger, impact.</body>\n</example>\n";
		expect(payloadProblems("agent", `${body}<critical>\n- NEVER.\n</critical>\n`)).toEqual([]);
	});

	test("reports out-of-order tags", () => {
		const problems = payloadProblems("skill", "<critical>\n- NEVER.\n</critical>\n<caution>\nCareful.\n</caution>\n<procedure>\n1. Step.\n</procedure>\n");
		expect(problems.some(problem => problem.message.includes("out of order"))).toBe(true);
	});

	test("allows a closing critical but not a third block", () => {
		const closing = "<critical>\n- NEVER.\n</critical>\n<procedure>\n1. Step.\n</procedure>\n<critical>\n- Done when verified.\n</critical>\n";
		expect(payloadProblems("skill", closing)).toEqual([]);
		const third = `${closing}<critical>\n- Again.\n</critical>\n`;
		expect(payloadProblems("skill", third).map(problem => problem.message)).toContain(
			"<critical> appears more than twice; keep one opening and one closing block",
		);
	});

	test("reports a prohibition inside instruction", () => {
		const problems = payloadProblems("skill", "<critical>\n- NEVER.\n</critical>\n<instruction>\n- MUST check the name.\n</instruction>\n");
		expect(problems.map(problem => problem.message)).toContain("prohibition inside <instruction>; move it to <critical>");
	});

	test("reports advice inside critical", () => {
		const problems = payloadProblems("skill", "<critical>\n- SHOULD prefer drafts.\n</critical>\n");
		expect(problems.map(problem => problem.message)).toContain("advisory word inside <critical>; move it to <instruction>");
	});

	test("allows prohibitions in caution and procedure", () => {
		const body = "<critical>\n- NEVER.\n</critical>\n<procedure>\n1. MUST verify.\n</procedure>\n<caution>\n- NEVER treat empty output as clean.\n</caution>\n";
		expect(payloadProblems("skill", body)).toEqual([]);
	});

	test("reports an unknown tag with the allowed set", () => {
		const problems = payloadProblems("skill", "<critical>\n- NEVER.\n</critical>\n<workflow>\n1. Step.\n</workflow>\n");
		expect(problems.map(problem => problem.message)).toContain("<workflow> is retired; use <procedure>");
	});

	test("reports host-owned tags", () => {
		const problems = payloadProblems("rule", "<critical>\n- NEVER.\n</critical>\n<system-reminder>\nx\n</system-reminder>\n");
		expect(problems.some(problem => problem.message.includes("host-owned"))).toBe(true);
	});

	test("ignores tag mentions inside inline code", () => {
		expect(payloadProblems("skill", "<critical>\n- NEVER. Tags live in `<instruction>` blocks.\n</critical>\n")).toEqual([]);
	});

	test("requires critical in agents and commands", () => {
		expect(payloadProblems("agent", "You are a reviewer.\n").map(problem => problem.message)).toContain(
			"agent payloads MUST open with <critical>",
		);
		expect(payloadProblems("command", "<procedure>\n1. Step.\n</procedure>\n").map(problem => problem.message)).toContain(
			"command payloads MUST open with <critical>",
		);
	});

	test("requires critical once a skill or rule uses any tag", () => {
		const problems = payloadProblems("rule", "<procedure>\n1. Step.\n</procedure>\n");
		expect(problems.map(problem => problem.message)).toContain("a tagged rule payload MUST include <critical>");
	});
});
