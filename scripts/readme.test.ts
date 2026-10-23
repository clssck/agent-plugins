import { describe, expect, test } from "bun:test";
import { type Commit, commitStamp, renderReadme } from "./sync";

const LOCAL_REPO = "clssck/agent-plugins";
const UPSTREAM_REPO = "someone/skills";
const LOCAL_SHA = "1".repeat(40);
const UPSTREAM_SHA = "2".repeat(40);
const PIN_SHA = "3".repeat(40);
const DATE = "2026-01-02T03:04:05Z";

const sources = { repository: LOCAL_REPO, description: "test", upstreams: [] };
const empty = { requires: {}, optional: [] };
const base = { version: "1.0.0", attribution: false, skillReferences: empty, rules: [], agents: [], commands: [], tools: [], extensions: 0 };
const localPack = { ...base, name: "local-pack", dir: "packs/local-pack", skills: [{ name: "mine", file: "skills/mine/SKILL.md" }] };
const upstreamPack = {
	...base,
	name: "up-pack",
	dir: "upstream/up-pack",
	upstream: { name: "up-pack", repo: UPSTREAM_REPO, ref: "main", sha: PIN_SHA, description: "", include: { skills: "skills" } },
	origins: { skills: "skills" },
	skills: [{ name: "theirs", file: "skills/theirs/SKILL.md" }],
};

function commits() {
	const local = new Map<string, Commit>([
		["packs/local-pack", { repository: LOCAL_REPO, sha: LOCAL_SHA, date: DATE }],
		["packs/local-pack/skills/mine/SKILL.md", { repository: LOCAL_REPO, sha: LOCAL_SHA, date: DATE }],
		["upstream/up-pack", { repository: LOCAL_REPO, sha: LOCAL_SHA, date: DATE }],
	]);
	const upstream = new Map<string, Commit>([["up-pack/skills/theirs", { repository: UPSTREAM_REPO, sha: UPSTREAM_SHA, date: DATE }]]);
	return { local, upstream };
}

describe("README commit links", () => {
	test("commitStamp links the commit in the repository that owns it", () => {
		expect(commitStamp({ repository: UPSTREAM_REPO, sha: UPSTREAM_SHA, date: DATE })).toBe(
			`[2026-01-02 03:04 UTC](https://github.com/${UPSTREAM_REPO}/commit/${UPSTREAM_SHA})`,
		);
		expect(commitStamp(undefined)).toBe("—");
	});

	test("a local SHA is never linked under an upstream repository, nor an upstream SHA under this one", async () => {
		const readme = await renderReadme(sources, [localPack, upstreamPack] as never, commits());
		const links = [...readme.matchAll(/https:\/\/github\.com\/([^/\s)]+\/[^/\s)]+)\/commit\/([0-9a-f]{40})/g)].map(match => `${match[1]}@${match[2]}`);
		expect(links.length).toBeGreaterThan(0);
		for (const link of links) {
			expect([`${LOCAL_REPO}@${LOCAL_SHA}`, `${UPSTREAM_REPO}@${UPSTREAM_SHA}`]).toContain(link);
		}
		// The upstream pack's own row dates upstream/up-pack, a directory of this repository.
		const packRow = readme.split("\n").find(line => line.startsWith("| `up-pack` | `1.0.0`"));
		expect(packRow).toContain(`https://github.com/${LOCAL_REPO}/commit/${LOCAL_SHA}`);
		const itemRow = readme.split("\n").find(line => line.startsWith("| [theirs]"));
		expect(itemRow).toContain(`https://github.com/${UPSTREAM_REPO}/commit/${UPSTREAM_SHA}`);
		const localItemRow = readme.split("\n").find(line => line.startsWith("| [mine]"));
		expect(localItemRow).toContain(`https://github.com/${LOCAL_REPO}/commit/${LOCAL_SHA}`);
	});

	test("the License section describes the repository-wide MIT coverage", async () => {
		const readme = await renderReadme(sources, [localPack] as never, { local: new Map(), upstream: new Map() });
		expect(readme).toContain("covers all material authored in this repository");
		expect(readme).toContain("`local-pack`");
	});

	test("normal item rows render exactly as plain links", async () => {
		const readme = await renderReadme(sources, [localPack] as never, commits());
		expect(readme).toContain(`| [mine](https://github.com/${LOCAL_REPO}/blob/${LOCAL_SHA}/packs/local-pack/skills/mine/SKILL.md) | \`local-pack\` |`);
	});

	test("labels escape table and link syntax; every path segment is percent-encoded", async () => {
		const file = "skills/a b#c?d(e)/SKILL.md";
		const pack = { ...localPack, skills: [{ name: "pipe|[x]\\y", file }] };
		const readme = await renderReadme(sources, [pack] as never, { local: new Map(), upstream: new Map() });
		const row = readme.split("\n").find(line => line.startsWith("| [pipe"))!;
		expect(row.startsWith("| [pipe\\|\\[x\\]\\\\y](")).toBe(true);
		expect(row).toContain(`](https://github.com/${LOCAL_REPO}/blob/main/packs/local-pack/skills/a%20b%23c%3Fd%28e%29/SKILL.md) |`);
	});

	test("upstream item URLs encode the upstream path the same way", async () => {
		const pack = { ...upstreamPack, skills: [{ name: "odd", file: "skills/x y#z/SKILL.md" }] };
		const readme = await renderReadme(sources, [pack] as never, { local: new Map(), upstream: new Map() });
		const row = readme.split("\n").find(line => line.startsWith("| [odd]"))!;
		expect(row).toContain(`](https://github.com/${UPSTREAM_REPO}/blob/${PIN_SHA}/skills/x%20y%23z/SKILL.md) |`);
	});
});
