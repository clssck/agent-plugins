import { strict as assert } from "node:assert";

interface ToolResult {
	content: Array<{ type: string; text?: string }>;
}
interface RuntimeTool {
	execute(
		id: string,
		params: Record<string, unknown>,
		onUpdate: undefined,
		ctx: unknown,
		signal?: AbortSignal,
	): Promise<ToolResult>;
	onSession?(event: { reason: string }, ctx: unknown): void | Promise<void>;
}

/** Binds and exercises the host-created tool; no live model, network service, or debug socket is required. */
export async function checkTuiLifecycle(tool: RuntimeTool): Promise<void> {
	const name = "omp-loader-smoke";
	const invoke = (params: Record<string, unknown>, signal?: AbortSignal) =>
		tool.execute("host-smoke", { name, ...params }, undefined, {}, signal);
	const text = (result: ToolResult) => result.content.flatMap((item) => item.text ?? []).join("\n");
	try {
		await assert.rejects(invoke({ op: "start", bin: process.execPath }, AbortSignal.abort()));
		const started = await invoke({
			op: "start",
			bin: "/bin/sh",
			args: ["-c", 'printf "omp-ready\\n"; while IFS= read -r line; do printf "echo:%s\\n" "$line"; done'],
		});
		assert.match(text(started), /omp-ready/);
		await invoke({ op: "send", text: "hello\\n" });
		assert.match(text(await invoke({ op: "screen" })), /echo:hello/);
		await invoke({ op: "resize", cols: 60, rows: 12 });
		assert.match(text(await invoke({ op: "list" })), /60x12 running/);
		await invoke({ op: "stop" });
		assert.doesNotMatch(text(await invoke({ op: "list" })), /omp-loader-smoke/);
	} finally {
		await tool.onSession?.({ reason: "shutdown" }, {});
	}
}
