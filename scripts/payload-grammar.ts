/**
 * Structural contract for tagged capability payloads.
 *
 * The grammar is small on purpose: five tags, fixed order, no nesting. A malformed tag does not fail loudly at
 * runtime — it leaks literal text into a prompt as if it were a tag, or makes a constraint read as decoration. So the
 * repository checks structure statically instead of trusting review.
 */

export const TAGS = ["critical", "instruction", "procedure", "caution", "example"] as const;

export type Tag = (typeof TAGS)[number];

/** Harness-owned names. Authoring one inside a payload impersonates host content. */
const RESERVED = [
	"system-reminder",
	"system-interrupt",
	"system-notice",
	"system-notification",
	"system-injection",
	"role",
	"objective",
	"directives",
] as const;

/** Retired names and their replacement, so a rename cannot silently reintroduce a second vocabulary. */
const RENAMED: Record<string, Tag> = {
	workflow: "procedure",
	when: "instruction",
	"anti-patterns": "caution",
};

const RANK: Record<Tag, number> = {
	critical: 0,
	instruction: 1,
	procedure: 2,
	caution: 3,
	example: 4,
};

export type PayloadKind = "skill" | "rule" | "agent" | "command";

export interface PayloadProblem {
	line: number;
	message: string;
}

/** GitHub heading slug: lowercase, punctuation dropped, each space to a hyphen, hyphens never collapsed. */
export function headingSlug(heading: string): string {
	return heading
		.trim()
		.toLowerCase()
		.replace(/[^\p{L}\p{N}\p{M}\p{Pc}\s-]/gu, "")
		.replace(/\s/g, "-");
}

/** Blank out frontmatter and fenced blocks; inline code stays, since headings may contain it. */
export function maskFences(text: string): string {
	const lines = text.split("\n");
	let fenced = false;
	let frontmatter = false;
	return lines
		.map((line, index) => {
			if (index === 0 && line.trim() === "---") {
				frontmatter = true;
				return "";
			}
			if (frontmatter) {
				if (line.trim() === "---") frontmatter = false;
				return "";
			}
			if (/^\s*(```|~~~)/.test(line)) {
				// A fence toggles: the opening and closing lines are never payload either.
				fenced = !fenced;
				return "";
			}
			return fenced ? "" : line;
		})
		.join("\n");
}

/** Mask frontmatter, fences, and inline code so a mention of a tag is not read as a use. */
export function maskNonPayload(text: string): string {
	return maskFences(text).replace(/`[^`\n]*`/g, code => " ".repeat(code.length));
}

/**
 * Problems that make a payload's tag structure wrong. `parent` describes where the payload sits, so a caller can
 * prefix it with the pack and file.
 */
export function payloadProblems(kind: PayloadKind, text: string): PayloadProblem[] {
	const problems: PayloadProblem[] = [];
	const masked = maskNonPayload(text);
	const open: Array<{ name: string; line: number }> = [];
	const seen = new Map<string, number>();
	let lastRank = -1;

	for (const match of masked.matchAll(/<(\/?)([a-z][a-z0-9-]*)([^>]*)>/g)) {
		const [, closing, name, rest] = match;
		const line = masked.slice(0, match.index ?? 0).split("\n").length;
		if (!name) continue;
		const mention = `<${closing}${name}>`;

		if (rest && rest.trim() !== "/" && rest.trim() !== "") {
			problems.push({ line, message: `${mention} takes no attributes` });
			continue;
		}
		const reserved = (RESERVED as readonly string[]).includes(name);
		if (reserved) {
			problems.push({ line, message: `${mention} is host-owned; authoring it impersonates system content` });
			continue;
		}
		const renamed = RENAMED[name];
		if (renamed) {
			problems.push({ line, message: `${mention} is retired; use <${renamed}>` });
			continue;
		}
		const rank = name in RANK ? RANK[name as Tag] : undefined;
		if (rank === undefined) {
			problems.push({ line, message: `${mention} is not in the grammar; allowed: ${TAGS.join(", ")}` });
			continue;
		}

		if (!closing) {
			if (open.length > 0) {
				problems.push({ line, message: `${mention} nests inside <${open[open.length - 1]!.name}>; tags never nest` });
				continue;
			}
			if (name === "critical" && (seen.get("critical") ?? 0) >= 2) {
				problems.push({ line, message: `${mention} appears more than twice; keep one opening and one closing block` });
				continue;
			}
			if (name !== "critical" && rank < lastRank) {
				problems.push({ line, message: `${mention} is out of order; emit critical, instruction, procedure, caution, example` });
			}
			// <critical> may open once at the start and once at the end, so it never constrains the others' order.
			if (name !== "critical") lastRank = rank;
			open.push({ name, line });
			seen.set(name, (seen.get(name) ?? 0) + 1);
			continue;
		}

		const top = open.pop();
		if (!top) {
			problems.push({ line, message: `${mention} closes a tag that is not open` });
			continue;
		}
		if (top.name !== name) {
			problems.push({ line, message: `${mention} closes <${top.name}> opened on line ${top.line}` });
			continue;
		}
	}

	for (const unclosed of open) {
		problems.push({ line: unclosed.line, message: `<${unclosed.name}> is never closed` });
	}

	const hasCritical = (seen.get("critical") ?? 0) > 0;
	const anyTag = seen.size > 0;
	if ((kind === "agent" || kind === "command") && !hasCritical) {
		problems.push({ line: 1, message: `${kind} payloads MUST open with <critical>` });
	}
	if ((kind === "skill" || kind === "rule") && anyTag && !hasCritical) {
		problems.push({ line: 1, message: `a tagged ${kind} payload MUST include <critical>` });
	}

	return problems.sort((a, b) => a.line - b.line);
}
