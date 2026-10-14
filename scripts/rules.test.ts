import { describe, expect, test } from "bun:test";
import { readdir } from "node:fs/promises";
import * as path from "node:path";

const ROOT = path.resolve(import.meta.dir, "..");
const FRAGMENTS = path.join(ROOT, "rule-sources", "fragments");
const SHIPPED_RULES = path.join(ROOT, "packs", "clssck-core", "rules");

interface ShippedRule {
	name: string;
	conditions: string[];
	scopes: string[];
}

const toList = (value: unknown): string[] => (value === undefined ? [] : Array.isArray(value) ? value.map(String) : [String(value)]);

/** Load the generated rules exactly as they ship in packs/clssck-core/rules, parsing only their YAML frontmatter. */
async function loadShippedRules(): Promise<ShippedRule[]> {
	const rules: ShippedRule[] = [];
	for (const file of (await readdir(SHIPPED_RULES)).filter(name => name.endsWith(".md")).sort()) {
		const source = await Bun.file(path.join(SHIPPED_RULES, file)).text();
		expect(source.startsWith("---\n"), `${file} must open with frontmatter`).toBe(true);
		const end = source.indexOf("\n---", 3);
		expect(end, `${file} must have closed frontmatter`).toBeGreaterThan(0);
		const frontmatter = Bun.YAML.parse(source.slice(4, end)) as { condition?: unknown; scope?: unknown };
		rules.push({ name: file.slice(0, -".md".length), conditions: toList(frontmatter.condition), scopes: toList(frontmatter.scope) });
	}
	return rules;
}

/** Same translation as OMP's compileRuleCondition: a leading `(?ims)` group becomes native RegExp flags. */
function compileCondition(pattern: string): RegExp {
	const match = /^\(\?([a-z]+)\)/.exec(pattern);
	if (match && /^[ims]+$/.test(match[1])) return new RegExp(pattern.slice(match[0].length), Array.from(new Set(match[1])).join(""));
	return new RegExp(pattern);
}

const shipped = await loadShippedRules();
const compiled = new Map(shipped.map(rule => [rule.name, rule.conditions.map(compileCondition)]));

/** OMP matches bash arguments either as raw streamed text or as the final `{"command":"..."}` JSON snapshot. */
function matches(rule: string, command: string): { raw: boolean; json: boolean } {
	const conditions = compiled.get(rule);
	if (!conditions) throw new Error(`unknown rule ${rule}`);
	const json = JSON.stringify({ command });
	return { raw: conditions.some(condition => condition.test(command)), json: conditions.some(condition => condition.test(json)) };
}

const dq = (command: string) => `"${command.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
const sq = (command: string) => `'${command.replaceAll("'", `'\\''`)}'`;

/** Every wrapper shape a command can hide in, with the quote style it needs around the inner command. */
const wrapperShapes: Array<[label: string, quote: '"' | "'", build: (quoted: string) => string]> = [
	["bash -c", '"', quoted => `bash -c ${quoted}`],
	["sh -c", "'", quoted => `sh -c ${quoted}`],
	["/bin/bash -lc", '"', quoted => `/bin/bash -lc ${quoted}`],
	["sudo bash -c", "'", quoted => `sudo bash -c ${quoted}`],
	["sudo -u env zsh -lc", '"', quoted => `sudo -u deploy env A=1 /usr/bin/zsh -lc ${quoted}`],
	["dash -c", "'", quoted => `dash -c ${quoted}`],
	["ksh -c", '"', quoted => `ksh -c ${quoted}`],
	["ssh host", '"', quoted => `ssh host ${quoted}`],
	["ssh options", "'", quoted => `ssh -p 2222 -o BatchMode=yes -tt user@host.example ${quoted}`],
];

/** Shell text that may follow a closing wrapper quote while the inner command still ends exactly at that quote. */
const wrapperTails = ["", ";", " ; echo done", " && echo done", " || true", "|cat", "\necho done", " &"];

/**
 * Wrap `command` in every shape whose quote character does not occur in the command, so no escaping is needed.
 * The inner command always ends at the closing wrapper quote, which is followed by nothing, a control operator,
 * a newline, or the `)` of a subshell.
 */
function wrap(command: string): Array<[label: string, wrapped: string]> {
	return wrapperShapes
		.filter(([, quote]) => !command.includes(quote))
		.flatMap(([label, quote, build]) => {
			const wrapped = build(`${quote}${command}${quote}`);
			return [
				...wrapperTails.map((tail): [string, string] => [tail ? `${label} then ${JSON.stringify(tail)}` : label, `${wrapped}${tail}`]),
				[`(${label})`, `(${wrapped})`],
			];
		});
}

interface Matrix {
	/** Commands the rule must flag as written. */
	positives: string[];
	/** Commands the rule must not flag, in raw and JSON form. */
	negatives: string[];
	/** Commands the rule must also flag inside every wrapper and after `cd ...;`. */
	wrapped: string[];
}

const matrix: Record<string, Matrix> = {
	"build-cache-deletion-safety": {
		positives: ["rm -rf node_modules", "rm -rf ~/.cache/uv", "sudo rm -rf target"],
		negatives: ["rm file.txt", "ls node_modules", "grep -rn node_modules src", "rm -rf node_modules' backup'", `rm -rf node_modules" backup"`],
		wrapped: ["rm -rf node_modules"],
	},
	"dbt-command-scope": {
		positives: ["dbt build", "dbt run --empty", "dbt build --full-refresh --target prod", "uv run dbt build"],
		negatives: ["dbt run --select my_model", "dbt test --select my_model", "dbt ls", "dbt compile", "dbt parse", "dbt docs generate", "dbt --version"],
		wrapped: ["dbt build", "dbt run --empty"],
	},
	"docker-data-safety": {
		positives: ["docker system prune -af", "docker volume rm data", "docker volume prune", "docker compose down -v", "docker builder prune"],
		negatives: ["docker ps", "docker images", "docker logs web", "docker volume ls", "docker inspect web"],
		wrapped: ["docker system prune -af", "docker volume rm data", "docker volume prune", "docker builder prune"],
	},
	"gh-external-mutation-safety": {
		positives: ["gh pr create --title x", "gh pr merge 12", "gh pr merge", "gh issue comment 3 --body hi", "gh release create v1", "gh api -X POST repos/o/r/issues"],
		negatives: ["gh pr view 12", "gh pr list", "gh pr status", "gh issue view 3", "gh api repos/o/r", "gh repo view"],
		wrapped: ["gh pr merge 12", "gh pr merge", "gh pr create --title x"],
	},
	"git-commit-conventions": {
		positives: ["git add -A", "git add .", "git add -u", "git commit -a -m x", "git commit -am x"],
		negatives: ["git add src/a.ts", "git commit -m x", "git add -p", "git status"],
		wrapped: ["git add -A", "git add .", "git commit -am x"],
	},
	"git-push-safety": {
		positives: ["git push", "git push --force", "git push origin main", "git -C repo push origin main", "git push --force origin feature", "cd /tmp/repo && git push origin main", "cd repo; git push origin main"],
		negatives: ["git push --dry-run origin main", "git push -n origin main", "git push --dry-run", "git push -n", "git status", "git log origin/main"],
		wrapped: ["git push", "git push --force", "git push origin main", "cd /tmp/repo && git push origin main", "cd repo; git push origin main"],
	},
	"git-worktree-restore-safety": {
		positives: ["git restore .", "git checkout -- .", "git clean -fd", "git reset --hard"],
		negatives: ["git status", "git diff", "git clean -n"],
		wrapped: ["git clean -fd", "git reset --hard", "git restore .", "git checkout -- ."],
	},
	"sql-mutation-safety": {
		positives: ["psql -c 'DELETE FROM users'", "sqlite3 app.db 'DELETE FROM t'", "snowsql -q 'TRUNCATE TABLE t'", "psql -c 'DROP TABLE users'", "rails db:drop"],
		negatives: ["psql -c 'select 1'", "psql -c 'SELECT * FROM users'", "dbt run-operation noop"],
		wrapped: ["psql -c 'DELETE FROM users'", "sqlite3 app.db 'DELETE FROM t'", "rails db:drop"],
	},
	"temp-cleanup-ownership": {
		positives: ["rm -rf /tmp/*", "rm -rf $TMPDIR/*", "find /tmp -mtime +1 -delete"],
		negatives: ["ls /tmp", "rm -rf /tmp/mydir-123", "find /tmp -name x"],
		wrapped: ["rm -rf /tmp/*", "find /tmp -mtime +1 -delete"],
	},
};

/** Prose, lookalike binaries and non-shell wrappers that must never be treated as the target command or a wrapper. */
const lookalikes = (command: string): string[] => [
	`echo ${dq(command)}`,
	`echo ${dq(`bash -c ${dq(command)}`)}`,
	`grep -c ${sq(command)} notes.txt`,
	`fresh -c ${sq(command)}`,
	`ssh-keygen -c ${sq(command)}`,
	`ssh-add host ${sq(command)}`,
	`bash script.sh ${dq(command)}`,
	`bash -x ${dq(command)}`,
];

describe("shipped rules compile", () => {
	test("fragments are one-line RegExp sources", async () => {
		const fragments = (await readdir(FRAGMENTS)).filter(name => name.endsWith(".regex")).sort();
		expect(fragments).toEqual(expect.arrayContaining(["json-command-start.regex", "shell-command-start.regex"]));
		for (const fragment of fragments) {
			const text = await Bun.file(path.join(FRAGMENTS, fragment)).text();
			const source = text.replace(/\r?\n$/, "");
			expect(source, fragment).not.toMatch(/[\r\n]/);
			expect(() => new RegExp(source), fragment).not.toThrow();
		}
	});

	test("every condition compiles the way OMP compiles it", () => {
		for (const rule of shipped) {
			expect(rule.conditions.length, rule.name).toBeGreaterThan(0);
			for (const [index, condition] of rule.conditions.entries()) {
				expect(() => compileCondition(condition), `${rule.name} condition[${index}]`).not.toThrow();
			}
		}
	});

	test("the matrix covers exactly the bash-scoped rules", () => {
		const bashScoped = shipped.filter(rule => rule.scopes.some(scope => scope === "tool:bash" || scope.startsWith("tool:bash("))).map(rule => rule.name);
		expect(Object.keys(matrix).sort()).toEqual(bashScoped.sort());
	});
});

describe("bash command rules", () => {
	for (const [rule, cases] of Object.entries(matrix)) {
		describe(rule, () => {
			test("flags ordinary commands as raw text and as OMP's JSON snapshot", () => {
				for (const command of cases.positives) {
					expect(matches(rule, command), command).toEqual({ raw: true, json: true });
				}
			});

			test("flags commands inside shell and ssh wrappers", () => {
				for (const command of cases.wrapped) {
					for (const [label, wrappedCommand] of wrap(command)) {
						expect(matches(rule, wrappedCommand), `${label}: ${wrappedCommand}`).toEqual({ raw: true, json: true });
					}
				}
			});

			test("flags commands after sudo/env prefixes", () => {
				for (const command of cases.wrapped) {
					for (const prefixed of [`sudo ${command}`, `env A=1 ${command}`, `A=1 ${command}`]) {
						expect(matches(rule, prefixed), prefixed).toEqual({ raw: true, json: true });
					}
				}
			});

			test("leaves safe forms, prose, and lookalike binaries alone", () => {
				for (const command of cases.negatives) {
					expect(matches(rule, command), command).toEqual({ raw: false, json: false });
				}
				for (const command of cases.wrapped) {
					for (const lookalike of lookalikes(command)) {
						expect(matches(rule, lookalike), lookalike).toEqual({ raw: false, json: false });
					}
				}
				for (const command of cases.negatives) {
					for (const [label, wrappedCommand] of wrap(command)) {
						expect(matches(rule, wrappedCommand), `${label}: ${wrappedCommand}`).toEqual({ raw: false, json: false });
					}
				}
			});
		});
	}
});

describe("nested wrappers", () => {
	test("git push is flagged through shell-in-ssh and shell-in-shell nesting with a cd prefix", () => {
		for (const command of [
			`bash -c "ssh host 'cd repo; git push origin main'"`,
			`sh -c 'bash -c "cd /tmp/repo && git push origin main"'`,
			`sudo bash -c 'ssh -p 22 host "git push origin main"'`,
		]) {
			expect(matches("git-push-safety", command), command).toEqual({ raw: true, json: true });
		}
	});
});

describe("wrapper quote boundaries", () => {
	const none = { raw: false, json: false };
	const flagged = { raw: true, json: true };

	test("a wrapper's closing quote ends the scan: later quoted arguments are not commands", () => {
		for (const command of [`bash -c 'true' 'ignored; rm -rf node_modules'`, `bash -c "true" "ignored; rm -rf node_modules"`, `sh -c 'true' "ignored; rm -rf node_modules"`]) {
			expect(matches("build-cache-deletion-safety", command), command).toEqual(none);
		}
	});

	test("a quote followed by more words is not a token boundary", () => {
		for (const command of [`rm -rf node_modules' backup'`, `rm -rf node_modules" backup"`, `bash -c "rm -rf node_modules' backup'"`]) {
			expect(matches("build-cache-deletion-safety", command), command).toEqual(none);
		}
	});

	test("dry-run pushes stay exempt inside wrappers", () => {
		for (const command of [`bash -c 'git push --dry-run'`, `bash -c "git push --dry-run"`, `bash -c 'git push -n'`, `bash -c "git push -n"`, `sh -c 'git push --dry-run origin main'`, `ssh host "git push -n"`]) {
			expect(matches("git-push-safety", command), command).toEqual(none);
		}
	});

	// A double-quoted wrapper body is decoded once by the outer shell before the inner shell parses it: `\\` becomes
	// `\`, `\"` becomes `"`, and every other `\x` keeps its backslash. A run of n backslashes before `;` therefore
	// reaches the inner shell as ceil(n / 2) backslashes, and the `;` separates commands only when that count is even,
	// i.e. n % 4 is 0 or 3. A single-quoted body is passed through verbatim, so only the parity of n matters.
	// The strings below are runtime strings (checked against real bash), not TypeScript escape sequences: two
	// backslash characters is what `bash -c "echo foo\\; git push"` contains when typed in a terminal.
	test("backslashes before `;` in a double-quoted wrapper are decoded once by the outer shell", () => {
		// 2 backslashes: the outer shell turns `\\` into `\`, the inner shell sees the escaped `\;` and runs one echo.
		const twoBackslashes = String.raw`bash -c "echo foo\\; git push"`;
		expect(matches("git-push-safety", twoBackslashes), twoBackslashes).toEqual(none);
		// 3 backslashes: `\\` becomes `\` and `\;` stays, so the inner shell sees `\\;`: an escaped backslash, then a separator.
		const threeBackslashes = String.raw`bash -c "echo foo\\\; git push"`;
		expect(matches("git-push-safety", threeBackslashes), threeBackslashes).toEqual(flagged);

		const dqDecoded = (count: number) => count % 4 === 0 || count % 4 === 3;
		const targets: Array<[rule: string, command: string]> = [
			["git-push-safety", "git push"],
			["build-cache-deletion-safety", "rm -rf node_modules"],
		];
		// Each shape embeds `echo foo<count backslashes>; <command>`; `separates` says whether the `;` splits commands.
		const shapes: Array<[label: string, build: (body: string) => string, separates: (count: number) => boolean]> = [
			["double-quoted wrapper", body => `bash -c "${body}"`, dqDecoded],
			["double-quoted wrapper after a prefix", body => `sudo -u deploy env A=1 /bin/bash -lc "${body}"`, dqDecoded],
			["single-quoted wrapper", body => `sh -c '${body}'`, count => count % 2 === 0],
			["single-quoted ssh command inside a double-quoted wrapper", body => `bash -c "ssh host '${body}'"`, dqDecoded],
			["double-quoted ssh command inside a single-quoted wrapper", body => `bash -c 'ssh host "${body}"'`, dqDecoded],
			["double-quoted wrapper inside a single-quoted wrapper", body => `sh -c 'bash -c "${body}"'`, dqDecoded],
			["single-quoted wrapper inside a double-quoted wrapper", body => `bash -c "bash -c '${body}'"`, dqDecoded],
		];
		for (const [rule, command] of targets) {
			for (const [label, build, separates] of shapes) {
				for (let count = 0; count <= 8; count++) {
					const wrapped = build(`echo foo${"\\".repeat(count)}; ${command}`);
					expect(matches(rule, wrapped), `${label}, ${count} backslashes: ${wrapped}`).toEqual(separates(count) ? flagged : none);
				}
			}
		}
	});

	test("a dangerous command ending exactly at the wrapper quote is flagged", () => {
		const cases: Array<[rule: string, command: string]> = [
			["build-cache-deletion-safety", `bash -c "rm -rf node_modules"`],
			["dbt-command-scope", `bash -c "dbt build"`],
			["docker-data-safety", `bash -c "docker volume prune"`],
			["gh-external-mutation-safety", `bash -c "gh pr merge 12"`],
			["git-commit-conventions", `bash -c "git add -A"`],
			["git-push-safety", `bash -c "git push"`],
			["git-worktree-restore-safety", `sh -c 'git clean -fd'`],
			["sql-mutation-safety", `sh -c 'rails db:drop'`],
			["temp-cleanup-ownership", `sh -c 'find /tmp -mtime +1 -delete'`],
		];
		for (const [rule, command] of cases) {
			expect(matches(rule, command), `${rule}: ${command}`).toEqual(flagged);
		}
	});

	test("an opening quote is not a command boundary: quoted control text stays one operand", () => {
		const cases: Array<[rule: string, command: string]> = [
			["build-cache-deletion-safety", "rm -rf node_modules"],
			["dbt-command-scope", "dbt build"],
			["docker-data-safety", "docker volume prune"],
			["docker-data-safety", "docker builder prune"],
			["gh-external-mutation-safety", "gh pr merge"],
			["git-commit-conventions", "git add -A"],
			["git-commit-conventions", "git add ."],
			["git-push-safety", "git push"],
			["git-worktree-restore-safety", "git clean -fd"],
			["sql-mutation-safety", "rails db:drop"],
			["temp-cleanup-ownership", "find /tmp -mtime +1 -delete"],
		];
		for (const [rule, command] of cases) {
			for (const quote of ["'", '"']) {
				for (const content of [" ; backup", "; backup", " && backup", "|backup", "\nbackup"]) {
					for (const prefix of ["", "bash -c ", "ssh host "]) {
						// Outside a wrapper the quote opens a word; inside a wrapper of the other quote kind it is plain text.
						const other = quote === "'" ? '"' : "'";
						const direct = `${command}${quote}${content}${quote}`;
						const inWrapper = prefix ? `${prefix}${other}${direct}${other}` : direct;
						expect(matches(rule, inWrapper), `${rule}: ${inWrapper}`).toEqual(none);
					}
				}
			}
		}
	});

	// One dangerous command per bash-scoped rule; argument-free where possible so quote concatenation changes the target.
	const nestedTargets: Array<[rule: string, command: string]> = [
		["build-cache-deletion-safety", "rm -rf node_modules"],
		["dbt-command-scope", "dbt build"],
		["docker-data-safety", "docker volume prune"],
		["gh-external-mutation-safety", "gh pr merge"],
		["git-commit-conventions", "git add -A"],
		["git-push-safety", "git push"],
		["git-worktree-restore-safety", "git clean -fd"],
		["sql-mutation-safety", "rails db:drop"],
		["temp-cleanup-ownership", "find /tmp -mtime +1 -delete"],
	];

	test("nested-closure cases cover every bash-scoped rule", () => {
		expect(nestedTargets.map(([rule]) => rule).sort()).toEqual(Object.keys(matrix).sort());
	});

	// Known gaps, deliberately not covered: unquoted `ssh host cmd`, wrapper bodies with escaped inner quotes
	// (`bash -c "ssh host \"cmd\""`), and ssh `-o` options that change whether a remote command runs
	// (`-o SessionType=none`, `-o RemoteCommand=...`); `-o` values are treated as ordinary option arguments.
	// Outer-shell backslash-newline removal is not fully modeled: three backslashes before an actual newline inside
	// a double-quoted wrapper may be treated conservatively as a command boundary. Reminder rules prefer that false
	// positive to missing a destructive command; fully parsing shell quoting is out of scope for these regexes.
	// Two unescaped levels is the limit, and the inner wrapper must use the opposite quote kind. Inside a wrapper the
	// command prefix (sudo/env/assignment/ssh option words) is read without any quoted words, so a quoted prefix word
	// (`bash -c "sudo -u 'x y' git push"`) is deliberately not recognised: it could be the enclosing delimiter closing.
	// A wrapper is entered only when its first same-kind quote closes the body: optional blanks, then a control
	// operator, newline, `)`, backtick or the end. Words after that closure are positional parameters, so a target
	// followed by them (`bash -c 'git push' ignored`, `bash -c 'git push origin' --dry-run`) is deliberately not
	// recognised, and so is quote concatenation (`bash -c 'git push 'origin main' --dry-run'`, which runs
	// `git push origin`). These are accepted gaps of the quote-concatenation/positional-argument family, not fixed.
	// A recognised wrapper's delimiter must also not reappear anywhere after its closure (raw text, or the JSON
	// command string), because a target's operand scanner could pair the real closing quote with that later quote
	// (`bash -c 'rm x'; echo ' -rf node_modules'` must stay unflagged). The price is a conservative gap: a wrapper
	// followed by later same-delimiter text (`bash -c 'rm -rf node_modules'; echo 'x'`) is not recognised. The
	// opposite quote kind after the closure is fine, and an alternating nested wrapper is bound the same way for
	// both of its delimiters.
	test("a dangerous command ending at immediately nested wrapper closures is flagged", () => {
		for (const [rule, command] of nestedTargets) {
			for (const nested of [`bash -c "ssh host '${command}'"`, `sh -c 'bash -c "${command}"'`, `sudo bash -c 'ssh -p 22 host "${command}"'`, `bash -c "ssh host 'cd repo; ${command}'"`]) {
				for (const tail of ["", ";", " ; echo done", " && echo done", "|cat", "\necho done", " &"]) {
					expect(matches(rule, `${nested}${tail}`), `${rule}: ${nested}${tail}`).toEqual(flagged);
				}
				expect(matches(rule, `(${nested})`), `${rule}: (${nested})`).toEqual(flagged);
			}
		}
	});

	test("only the innermost wrapper's closing quote may precede an enclosing closure", () => {
		for (const [rule, command] of nestedTargets) {
			for (const concatenated of [
				// The other quote kind directly after the command opens or continues a word inside the inner wrapper.
				`bash -c '${command}" ; backup'`,
				`bash -c "ssh host '${command}"x'"`,
				`sh -c 'bash -c "${command}'x"'`,
				// After the inner closure the next quote opens a word that the inner shell reads as part of the command.
				`bash -c '${command}'"' ; backup'"`,
				`bash -c "${command}"'" ; backup"'`,
				// After the nested closures, more word characters still extend the inner command's last word.
				`bash -c "ssh host '${command}'"'x'`,
				`sh -c 'bash -c "${command}"'"x"`,
			]) {
				expect(matches(rule, concatenated), `${rule}: ${concatenated}`).toEqual(none);
			}
		}
	});

	test("only the opposite quote kind opens a nested wrapper, with or without prefixes and tails", () => {
		for (const [rule, command] of nestedTargets) {
			for (const nested of [
				`bash -c 'bash -c "${command}" ; backup'`,
				`bash -c "bash -c '${command}' ; backup"`,
				`bash -c 'sudo bash -c "${command}"'`,
				`bash -c "env A=1 ssh host '${command}'"`,
			]) {
				expect(matches(rule, nested), `${rule}: ${nested}`).toEqual(flagged);
			}
		}
	});

	// A quote never nests inside the same quote kind: the second quote closes the outer one, so the inner wrapper
	// receives only the first word of the command and the remaining words become positional parameters.
	test("same-quote pseudo-nesting closes the outer wrapper instead of nesting", () => {
		for (const [rule, command] of nestedTargets) {
			for (const quote of ["'", '"']) {
				for (const pseudo of [
					`bash -c ${quote}bash -c ${quote}${command}${quote} ; backup${quote}`,
					`sh -c ${quote}bash -c ${quote}${command}${quote}${quote}`,
					`bash -c ${quote}ssh host ${quote}${command}${quote} ; backup${quote}`,
					`ssh host ${quote}bash -c ${quote}${command}${quote}${quote}`,
					`sudo bash -c ${quote}cd repo; sudo bash -c ${quote}${command}${quote}${quote}`,
				]) {
					expect(matches(rule, pseudo), `${rule}: ${pseudo}`).toEqual(none);
				}
			}
		}
	});

	test("a quoted prefix word never reopens the enclosing delimiter", () => {
		for (const [rule, command] of nestedTargets) {
			for (const quote of ["'", '"']) {
				const other = quote === "'" ? '"' : "'";
				for (const pseudo of [
					`bash -c ${quote}sudo -u ${quote}x y${quote} ${command}${quote}`,
					`bash -c ${quote}A=${quote}x y${quote} ${command}${quote}`,
					`bash -c ${quote}ssh host ${quote}x y${quote} ${command}${quote}`,
					`bash -c ${quote}sudo -u ${quote}x y${quote} bash -c ${other}${command}${other}${quote}`,
					`bash -c ${quote}env A=${quote}x y${quote} bash -c ${other}${command}${other}${quote}`,
					`bash -c ${quote}ssh -p ${quote}x y${quote} host ${other}${command}${other}${quote}`,
					`bash -c ${quote}bash -c ${other}sudo -u ${other}x y${other} ${command}${other}${quote}`,
					`bash -c ${quote}bash -c ${other}sudo -u ${quote}x y${quote} ${command}${other}${quote}`,
				]) {
					expect(matches(rule, pseudo), `${rule}: ${pseudo}`).toEqual(none);
				}
			}
		}
	});

	test("unquoted sudo/env/ssh prefixes still reach a nested command", () => {
		for (const [rule, command] of nestedTargets) {
			for (const nested of [
				`bash -c 'sudo -u deploy env A=1 ${command}'`,
				`bash -c "sudo -u deploy env A=1 ssh -p 22 host '${command}'"`,
				`bash -c 'sudo -u x ssh -p 22 host "${command}"'`,
			]) {
				expect(matches(rule, nested), `${rule}: ${nested}`).toEqual(flagged);
			}
		}
	});

	test("a wrapper's first same-kind quote closes it, so later text never extends the inner command", () => {
		for (const quote of ["'", '"']) {
			// `rm file` runs; `x -rf node_modules` is the inert $0.
			const inert = `bash -c ${quote}rm ${quote}file x${quote} -rf node_modules${quote}`;
			expect(matches("build-cache-deletion-safety", inert), inert).toEqual(none);
			// `rm x` runs; the second quoted word is a positional parameter, not an operand of rm.
			const positional = `bash -c ${quote}rm x${quote} ${quote} -rf node_modules${quote}`;
			expect(matches("build-cache-deletion-safety", positional), positional).toEqual(none);
		}
		for (const exact of [`bash -c 'rm x' ' -rf node_modules'`, `bash -c "rm x" " -rf node_modules"`]) {
			expect(matches("build-cache-deletion-safety", exact), exact).toEqual(none);
		}
		// `rm x` runs; the quoted text after the control operator is a separate command, not an operand of rm.
		for (const quote of ["'", '"']) {
			for (const separator of ["; echo", " && echo", "\necho"]) {
				const later = `bash -c ${quote}rm x${quote}${separator} ${quote} -rf node_modules${quote}`;
				expect(matches("build-cache-deletion-safety", later), later).toEqual(none);
			}
		}
		for (const exact of [`bash -c 'rm x'; echo ' -rf node_modules'`, `bash -c 'rm x' && echo ' -rf node_modules'`, `bash -c "rm x"; echo " -rf node_modules"`, `bash -c "rm x" && echo " -rf node_modules"`]) {
			expect(matches("build-cache-deletion-safety", exact), exact).toEqual(none);
		}
		for (const [rule, command] of nestedTargets) {
			for (const quote of ["'", '"']) {
				const other = quote === "'" ? '"' : "'";
				for (const pseudo of [
					`bash -c ${quote}echo ${quote}x y${quote} ; ${command}${quote}`,
					`ssh host ${quote}echo ${quote}x y${quote} ; ${command}${quote}`,
					`bash -c ${other}ssh host ${quote}echo ${quote}x y${quote} ; ${command}${quote}${other}`,
					// The closure is followed by positional words, not by a control operator.
					`bash -c ${quote}${command}${quote} ${quote} -rf node_modules${quote}`,
					`bash -c ${quote}${command}${quote} ${quote} ; ${command}${quote}`,
					`bash -c ${quote}${command}${quote} ignored`,
					`bash -c ${quote}${command}${quote} ${other}x${other}`,
					`bash -c ${other}ssh host ${quote}${command}${quote} ${quote} y${quote}${other}`,
					// The closure is genuine, but the same delimiter reappears in later text.
					`bash -c ${quote}${command}${quote}; echo ${quote} -rf node_modules${quote}`,
					`bash -c ${quote}${command}${quote} && echo ${quote}x${quote}`,
					`bash -c ${quote}${command}${quote}\necho ${quote}x${quote}`,
					`bash -c ${other}ssh host ${quote}${command}${quote}${other}; echo ${quote}x${quote}`,
					`bash -c ${other}ssh host ${quote}${command}${quote}${other}; echo ${other}x${other}`,
				]) {
					expect(matches(rule, pseudo), `${rule}: ${pseudo}`).toEqual(none);
				}
				for (const real of [
					`bash -c ${quote}${command}; true${quote}`,
					`bash -c ${quote}${command}  ${quote} ; echo done`,
					`bash -c ${other}ssh host ${quote}${command}; true${quote}${other}`,
					`bash -c ${quote}${command}${quote} ; echo x && echo done`,
					`(bash -c ${quote}${command}${quote}) | cat`,
					// Only the opposite quote kind appears after the closure.
					`bash -c ${quote}${command}${quote}; echo ${other}x${other}`,
				]) {
					expect(matches(rule, real), `${rule}: ${real}`).toEqual(flagged);
				}
			}
		}
	});
});

describe("ssh modes that do not execute a shell command", () => {
	const none = { raw: false, json: false };
	const flagged = { raw: true, json: true };
	// Option shapes after which the quoted operand is not a command: -G/-V print and exit, -N runs nothing,
	// -O is a control command, -Q a query, -W a stdio forward target, -s a subsystem name.
	// The option letters are case-sensitive even in (?i) rules (-N is not -n, -s is not -S).
	// Known gaps, deliberately not covered: unquoted `ssh host cmd` and wrapper bodies with escaped inner quotes.
	const nonCommandOptions = [
		"-G", "-V", "-N", "-O exit", "-O check", "-Q cipher", "-W 10.0.0.1:22", "-s", "-s sftp",
		"-tN", "-Nt", "-NT", "-vG", "-GV", "-nV", "-qN", "-fN", "-ts", "-sT", "-Ns", "-tG -v", "-p 2222 -N", "-N -p 2222", "-o BatchMode=yes -G", "-tt -O exit", "-vvN",
	];

	test("quoted ssh operands are not flagged when the options mean no shell command runs", () => {
		for (const [rule, cases] of Object.entries(matrix)) {
			for (const command of cases.wrapped) {
				for (const options of nonCommandOptions) {
					for (const quote of ["'", '"']) {
						if (command.includes(quote)) continue;
						const ssh = `ssh ${options} user@host ${quote}${command}${quote}`;
						expect(matches(rule, ssh), `${rule}: ${ssh}`).toEqual(none);
					}
				}
			}
		}
	});

	test("ordinary ssh options and clusters still flag the quoted command", () => {
		for (const options of ["-t", "-tt", "-nT", "-fq", "-vvv", "-Y", "-X", "-4", "-A", "-J jump", "-i key", "-p 22 -tq", "-o BatchMode=yes", "-L 80:h:80", "-D 1080", "-S sock -tt", "--"]) {
			for (const [rule, cases] of Object.entries(matrix)) {
				const command = cases.wrapped[0];
				if (command.includes("'")) continue;
				const ssh = `ssh ${options} host '${command}'`;
				expect(matches(rule, ssh), `${rule}: ${ssh}`).toEqual(flagged);
			}
		}
	});

	test("nested ssh in a shell wrapper honours the same exclusions", () => {
		for (const command of [`bash -c "ssh -N host 'git push origin main'"`, `sh -c 'ssh -tG host "git push origin main"'`, `sudo bash -c 'ssh -O exit host "git push origin main"'`]) {
			expect(matches("git-push-safety", command), command).toEqual(none);
		}
	});
});
