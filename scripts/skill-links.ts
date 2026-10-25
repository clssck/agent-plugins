// skill:// link scanning and resolution, shared by sync.ts (packs) and check-skill.ts (skills shipped outside packs).

import { stat } from "node:fs/promises";
import * as path from "node:path";
import { headingSlug, maskFences } from "./payload-grammar";

export interface SkillLink {
  /** Lowercased skill name after `skill://`. */
  root: string;
  /** Path after the root, starting with `/`, trailing prose punctuation trimmed; empty for a bare root. */
  rawPath: string;
  /** 1-based line of the link in the scanned text. */
  line: number;
}

/** Every skill:// URI in a Markdown body, in order. */
export function skillLinks(contents: string): SkillLink[] {
  return Array.from(
    contents.matchAll(/\bskill:\/\/([a-z0-9][a-z0-9_-]*)(\/[^\s`<>"')\]}]+)?/gi),
    (match) => {
      const [, root = "", rawPath = ""] = match;
      return {
        root: root.toLowerCase(),
        rawPath: rawPath.replace(/[.,;:!?'"()\]}]+$/, ""),
        line: contents.slice(0, match.index ?? 0).split("\n").length,
      };
    },
  );
}

/**
 * Resolve a link inside the skill directory `baseDir` that `link.root` names; `scope` names where the target was
 * expected in the "does not exist" message. Returns the problem, or undefined when the link resolves.
 */
export async function skillLinkProblem(
  link: SkillLink,
  baseDir: string,
  scope: string,
): Promise<string | undefined> {
  const { root, rawPath } = link;
  if (!rawPath || rawPath === "/") {
    return undefined;
  }
  let relativePath: string;
  let fragment = "";
  try {
    const [beforeHash = "", hashPart = ""] = rawPath.slice(1).split("#", 2);
    const [withoutQuery = ""] = beforeHash.split("?", 1);
    relativePath = decodeURIComponent(withoutQuery);
    fragment = hashPart ? decodeURIComponent(hashPart) : "";
  } catch {
    return `invalid skill URI encoding in skill://${root}${rawPath}`;
  }
  const target = path.resolve(baseDir, relativePath);
  if (target !== baseDir && !target.startsWith(`${baseDir}${path.sep}`)) {
    return `skill URI escapes "${root}": skill://${root}${rawPath}`;
  }
  if (!(await stat(target).catch(() => {}))) {
    return `skill://${root}${rawPath} does not exist in ${scope}`;
  }
  if (fragment && /\.md$/i.test(target)) {
    // A stale anchor silently lands at the top of the file, so resolve it like the host's Markdown viewer.
    const headings = maskFences(await Bun.file(target).text()).matchAll(
      /^#{1,6}[ \t]+(.+?)[ \t]*$/gm,
    );
    const slugs = Array.from(headings, ([, heading = ""]) => headingSlug(heading));
    if (!slugs.includes(fragment.toLowerCase())) {
      return `skill://${root}${rawPath} has no heading "#${fragment}"`;
    }
  }
  return undefined;
}
