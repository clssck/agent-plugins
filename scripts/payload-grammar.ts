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
  "system-conventions",
  "objective",
  "project-context",
  "repo-rules",
  "file",
  "skills",
  "skill",
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

/** Levenshtein distance, capped by the caller's threshold. */
function editDistance(a: string, b: string): number {
  const width = b.length + 1;
  const cells = Array.from({ length: (a.length + 1) * width }, (_, k) =>
    k % width === 0 ? k / width : 0,
  );
  const cell = (i: number, j: number): number => {
    const value = cells[i * width + j];
    if (value === undefined) {
      throw new Error(`editDistance: cell ${i},${j} out of range`);
    }
    return value;
  };
  for (let j = 1; j <= b.length; j++) {
    cells[j] = j;
  }
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      cells[i * width + j] = Math.min(
        cell(i - 1, j) + 1,
        cell(i, j - 1) + 1,
        cell(i - 1, j - 1) + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
  }
  return cell(a.length, b.length);
}

/** A section name that looks like a mis-typed semantic tag would silently lose order and tier checks. */
function nearSemanticTag(name: string): Tag | undefined {
  return TAGS.find((tag) => name === `${tag}s` || editDistance(name, tag) <= 2);
}

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
    .replaceAll(/[^\p{L}\p{N}\p{M}\p{Pc}\s-]/gu, "")
    .replaceAll(/\s/g, "-");
}

/** Blank out frontmatter and fenced blocks; inline code stays, since headings may contain it. */
export function maskFences(text: string): string {
  const lines = text.split("\n");
  // An open fence closes only on the same character, at least as long as its opener, with nothing after it.
  let fence: { char: string; length: number } | undefined;
  let frontmatter = false;
  return lines
    .map((line, index) => {
      if (index === 0 && line.trim() === "---") {
        frontmatter = true;
        return "";
      }
      if (frontmatter) {
        if (line.trim() === "---") {
          frontmatter = false;
        }
        return "";
      }
      if (fence) {
        const closing = line.match(/^\s*(`{3,}|~{3,})\s*$/)?.[1];
        if (closing && closing[0] === fence.char && closing.length >= fence.length) {
          fence = undefined;
        }
        return "";
      }
      // A backtick fence's info string cannot contain a backtick; such a line is inline code, not a fence.
      const opening = line.match(/^\s*(`{3,}(?=[^`]*$)|~{3,})/)?.[1];
      if (opening) {
        fence = { char: opening.charAt(0), length: opening.length };
        return "";
      }
      return line;
    })
    .join("\n");
}

/** Mask frontmatter, fences, and inline code so a mention of a tag is not read as a use. */
export function maskNonPayload(text: string): string {
  // Double-backtick spans may contain single backticks, so match them first.
  return maskFences(text).replaceAll(/(``[\s\S]*?``|`[^`\n]*`)/g, (span) =>
    " ".repeat(span.length),
  );
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
    if (!name) {
      continue;
    }
    const mention = `<${closing}${name}>`;

    if (
      rest &&
      rest.trim() !== "/" &&
      rest.trim() !== "" &&
      !/^\s+[a-z-]+="[^"]*"\s*$/.test(rest)
    ) {
      problems.push({ line, message: `${mention} has malformed attributes; use name="value"` });
      continue;
    }
    const reserved = (RESERVED as readonly string[]).includes(name);
    if (reserved) {
      problems.push({
        line,
        message: `${mention} is host-owned; authoring it impersonates system content`,
      });
      continue;
    }
    const renamed = RENAMED[name];
    if (renamed) {
      problems.push({ line, message: `${mention} is retired; use <${renamed}>` });
      continue;
    }
    // Unknown lowercase-kebab names are section tags, the host's own idiom (`<directives>`, `<criteria>`,
    // `<findings>`). They carry structure only: no order constraint, no tier, and nesting is allowed.
    const ranks: Partial<Record<string, number>> = RANK;
    const rank = name in RANK ? ranks[name] : undefined;
    const section = rank === undefined;
    if (section) {
      const mistyped = nearSemanticTag(name);
      if (mistyped) {
        problems.push({ line, message: `${mention} looks like a mis-typed <${mistyped}>` });
        continue;
      }
    }
    if (!closing && section) {
      open.push({ name, line });
      continue;
    }
    if (closing && section) {
      const top = open.pop();
      if (!top) {
        problems.push({ line, message: `${mention} closes a tag that is not open` });
      } else if (top.name !== name) {
        problems.push({
          line,
          message: `${mention} closes <${top.name}> opened on line ${top.line}`,
        });
      }
      continue;
    }
    if (rank === undefined) {
      continue;
    }

    if (!closing) {
      if (name === "critical" && (seen.get("critical") ?? 0) >= 2) {
        problems.push({
          line,
          message: `${mention} appears more than twice; keep one opening and one closing block`,
        });
        continue;
      }
      if (name !== "critical" && rank < lastRank && open.length === 0) {
        problems.push({
          line,
          message: `${mention} is out of order; emit critical, instruction, procedure, caution, example`,
        });
      }
      // <critical> may open once at the start and once at the end, so it never constrains the others' order.
      if (name !== "critical" && open.length === 0) {
        lastRank = rank;
      }
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
      problems.push({
        line,
        message: `${mention} closes <${top.name}> opened on line ${top.line}`,
      });
      continue;
    }
  }

  for (const unclosed of open) {
    problems.push({ line: unclosed.line, message: `<${unclosed.name}> is never closed` });
  }

  // Tier check: a prohibition inside <instruction>, or advice inside <critical>, is the defect that survives
  // structural validation because the tag is closed correctly but carries the wrong kind of decision. It applies
  // only to the semantic tags at top level; section tags and nested blocks may mix modals, as the host's own do.
  const lines = masked.split("\n");
  const stack: string[] = [];
  lines.forEach((line, index) => {
    const opening = line.match(/^<([a-z][a-z0-9-]*)(?:\s[^>]*)?>[ \t]*$/);
    if (opening) {
      stack.push(opening[1] ?? "");
      return;
    }
    if (/^<\/[a-z][a-z0-9-]*>[ \t]*$/.test(line)) {
      stack.pop();
      return;
    }
    if (stack.length !== 1) {
      return;
    }
    const current = stack[0];
    if (current === "instruction" && /\b(MUST|NEVER)\b/.test(line)) {
      problems.push({
        line: index + 1,
        message: "prohibition inside <instruction>; move it to <critical>",
      });
    }
    if (current === "critical" && /\b(SHOULD|MAY)\b/.test(line)) {
      problems.push({
        line: index + 1,
        message: "advisory word inside <critical>; move it to <instruction>",
      });
    }
  });

  const hasCritical = (seen.get("critical") ?? 0) > 0;
  const anyTag = seen.size > 0;
  if (anyTag && !hasCritical) {
    problems.push({ line: 1, message: `a tagged ${kind} payload MUST include <critical>` });
  }

  return problems.toSorted((a, b) => a.line - b.line);
}
