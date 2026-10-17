import { afterEach, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import factory from "../packs/clssck-development/tools/tui";

// Schema construction is covered by the real OMP loader smoke; these tests exercise the PTY lifecycle.
const field = {
	describe() {
		return this;
	},
	optional() {
		return this;
	},
};
const tool = factory({
	cwd: process.cwd(),
	zod: {
		object: () => field,
		string: () => field,
		boolean: () => field,
		number: () => field,
		array: () => field,
	},
});
const dirs: string[] = [];
// Set only in executors that deny AF_UNIX binding; CI runs these scenarios.
const canBindSocket = process.env.OMP_SKIP_SOCKET_TESTS !== "1";
afterEach(async () => {
	tool.onSession({ reason: "shutdown" });
	await Promise.all(dirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

async function fixture(mode: "startup" | "read") {
	const dir = await mkdtemp(join(tmpdir(), "tui-lifecycle-"));
	dirs.push(dir);
	const marker = join(dir, "marker.json");
	const app = join(dir, "app.ts");
	await writeFile(
		app,
		`
import net from "node:net";
import { writeFileSync } from "node:fs";
const marker = ${JSON.stringify(marker)};
const mode = ${JSON.stringify(mode)};
const mark = () => writeFileSync(marker, JSON.stringify({pid:process.pid,socket:process.env.OMP_TUI_DEBUG}));
process.stdout.write("ready\\r\\n");
setInterval(() => {}, 1000);
if(mode === "startup") mark();
else net.createServer(socket => {
 let buffer = "";
 socket.on("error", () => {});
 socket.on("data", data => {
  buffer += data.toString();
  while(buffer.includes("\\n")) {
   const i = buffer.indexOf("\\n"); const body = JSON.parse(buffer.slice(0,i)); buffer = buffer.slice(i+1);
   if(body.op === "frame") { mark(); setTimeout(() => socket.write(JSON.stringify({lines:["stale reply"]})+"\\n"), 100); }
   else if(body.op === "quit") process.exit(0);
   else socket.write(JSON.stringify({ok:true, lines:["ready"],window_top:0})+"\\n");
  }
 });
}).listen(process.env.OMP_TUI_DEBUG);
`,
	);
	return { app, marker };
}
async function marker(path: string): Promise<{ pid: number; socket: string }> {
	const deadline = Date.now() + 5000;
	while (Date.now() < deadline) {
		try {
			return JSON.parse(await readFile(path, "utf8"));
		} catch {}
		await Bun.sleep(10);
	}
	throw new Error("fixture never reached the requested operation");
}

test("pre-cancelled start creates no session", async () => {
	await expect(
		tool.execute("cancelled", { op: "start", bin: process.execPath }, undefined, undefined, AbortSignal.abort()),
	).rejects.toThrow();
	expect((await tool.execute("list", { op: "list" })).content).toEqual([{ type: "text", text: "no sessions" }]);
});

test.skipIf(!canBindSocket)(
	"cancelling startup kills the new child and removes its session directory",
	async () => {
		const f = await fixture("startup");
		const abort = new AbortController();
		const starting = tool.execute(
			"start",
			{
				op: "start",
				name: "starting",
				bin: process.execPath,
				args: [f.app],
				debug: true,
				timeout: 15,
			},
			undefined,
			undefined,
			abort.signal,
		);
		const observed = starting.then(() => undefined, error => error);
		const child = await marker(f.marker);
		abort.abort();
		expect(await observed).toBeInstanceOf(Error);
		expect(() => process.kill(child.pid, 0)).toThrow();
		expect(existsSync(dirname(child.socket))).toBe(false);
		expect((await tool.execute("list", { op: "list" })).content).toEqual([{ type: "text", text: "no sessions" }]);
	},
	10000,
);

test.skipIf(!canBindSocket)(
	"cancelling a debug request preserves the PTY and cannot misassign a late reply",
	async () => {
		const f = await fixture("read");
		await tool.execute("start", {
			op: "start",
			name: "existing",
			bin: process.execPath,
			args: [f.app],
			debug: true,
		});
		const abort = new AbortController();
		const reading = tool.execute("read", { op: "frame", name: "existing" }, undefined, undefined, abort.signal);
		const observed = reading.then(() => undefined, error => error);
		const child = await marker(f.marker);
		abort.abort();
		expect(String(await observed)).toContain("cancelled");
		expect(process.kill(child.pid, 0)).toBe(true);
		expect((await tool.execute("screen", { op: "screen", name: "existing" })).content[0]).toMatchObject({
			type: "text",
			text: expect.stringContaining("ready"),
		});
		await expect(tool.execute("again", { op: "frame", name: "existing" })).rejects.toThrow("no debug socket");
		await tool.execute("stop", { op: "stop", name: "existing" });
		expect(existsSync(dirname(child.socket))).toBe(false);
	},
	10000,
);
