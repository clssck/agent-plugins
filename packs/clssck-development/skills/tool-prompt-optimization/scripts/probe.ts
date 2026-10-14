#!/usr/bin/env bun
/**
 * Schema -> prompt inference probe.
 *
 * Given a tool's JSON parameter schema + a description outline ("template"), ask the
 * caller-selected models to reconstruct the full description. Whatever they reliably
 * predict is inferable from schema/outline alone — a candidate to PRUNE from the
 * hand-written prompt. Trust only content STABLE across samples AND models.
 *
 * Model calls go through the OMP host model layer (`@oh-my-pi/pi-ai` `completeSimple`,
 * `@oh-my-pi/pi-catalog/models` `getBundledModel`), resolved from the current working
 * directory and loaded only after arguments validate. Credentials are whatever that host
 * layer resolves for the selected provider; this script names no provider, model, or key.
 *
 * CLI:
 *   bun probe.ts --schema <file|json> --template <file|text> --model <provider/id> [options]
 *     --model <provider/id>   REQUIRED unless CLSSCK_PROBE_MODELS is set. Repeatable;
 *                             each value MAY be comma-separated. Flag wins over env.
 *     --name <toolName>       tool name shown to the model (default "the tool")
 *     --samples <n>           independent samples per model, integer 1..20 (default 3)
 *     --max-tokens <n>        output cap, integer 1..32000 (default 1200)
 *     --json                  emit JSON instead of human-readable blocks
 *     --help                  print usage and exit 0
 *   CLSSCK_PROBE_MODELS       comma-separated provider/id list used when no --model is given.
 *   Invalid arguments print the error + usage and exit 2 before any model call.
 *
 * Programmatic: import { probe } from "./probe.ts" — `models` is required.
 */
import { type ParseArgsOptionsConfig, parseArgs } from "node:util";
import type * as PiAi from "@oh-my-pi/pi-ai";
import type { Api, AssistantMessage, Model } from "@oh-my-pi/pi-ai";
import type * as PiCatalog from "@oh-my-pi/pi-catalog/models";
import type { GeneratedProvider } from "@oh-my-pi/pi-catalog/models";

export const PROBE_MODELS_ENV = "CLSSCK_PROBE_MODELS";
const DEFAULT_SAMPLES = 3;
const MAX_SAMPLES = 20;
const DEFAULT_MAX_TOKENS = 1200;
const MAX_OUTPUT_TOKENS = 32000;
const MODEL_REF = /^[^\s/]+\/\S+$/;

/** Flags shared by every probe entry point; spread into a `parseArgs` options map. */
export const PROBE_FLAGS = {
	model: { type: "string", multiple: true },
	samples: { type: "string" },
	"max-tokens": { type: "string" },
	json: { type: "boolean" },
	help: { type: "boolean" },
} satisfies ParseArgsOptionsConfig;

export const PROBE_FLAGS_USAGE = [
	`  --model <provider/id>   repeatable, comma-separated allowed; required unless ${PROBE_MODELS_ENV} is set`,
	`  --samples <n>           samples per model, 1..${MAX_SAMPLES} (default ${DEFAULT_SAMPLES})`,
	`  --max-tokens <n>        output cap, 1..${MAX_OUTPUT_TOKENS} (default ${DEFAULT_MAX_TOKENS})`,
	"  --json                  emit JSON",
	"  --help                  print usage and exit",
	`  ${PROBE_MODELS_ENV}       env fallback: comma-separated provider/id list`,
].join("\n");

const USAGE = [
	"usage: bun probe.ts --schema <file|json> --template <file|text> --model <provider/id> [options]",
	"  --schema <file|json>    wire JSON schema: file path or inline JSON (required)",
	"  --template <file|text>  description outline: file path or inline text (required)",
	'  --name <toolName>       tool name shown to the model (default "the tool")',
	PROBE_FLAGS_USAGE,
].join("\n");

const SYSTEM_PROMPT = [
	"You write the description prompt that an AI coding agent reads to learn one of its tools.",
	"You are given ONLY the tool name and its JSON parameter schema, plus a fixed description outline.",
	"Fill in the outline: replace every `...` and write the body of every named section, grounded strictly in the schema.",
	"Output ONLY the finished description as markdown. No preamble, no commentary, no surrounding code fence.",
].join("\n");

/** Invalid caller input; entry points print it with usage and exit 2. */
export class UsageError extends Error {}

/** Every flag any probe entry point declares; unset flags are `undefined`. */
export interface ProbeCliValues {
	schema?: string;
	template?: string;
	name?: string;
	tool?: string;
	"no-summary"?: boolean;
	show?: boolean;
	model?: string[];
	samples?: string;
	"max-tokens"?: string;
	json?: boolean;
	help?: boolean;
}

export interface ProbeOptions {
	/** JSON Schema for the tool's parameters (object or JSON string). */
	schema: unknown;
	/** Description outline: a one-line summary + section skeleton (with `...` placeholders). */
	template: string;
	/** `provider/id` refs chosen by the caller. Required; no default panel. */
	models: string[];
	/** Tool name surfaced to the model. */
	name?: string;
	/** Independent samples per model. Only content stable across samples is trustworthy. */
	samples?: number;
	maxTokens?: number;
	signal?: AbortSignal;
}

export interface ProbeSample {
	text: string;
	stopReason: AssistantMessage["stopReason"];
	usage?: AssistantMessage["usage"];
	error?: string;
}

export interface ProbeModelResult {
	model: string;
	samples: ProbeSample[];
}

export interface ProbeRun {
	prompt: string;
	results: ProbeModelResult[];
}

export interface ProbeSettings {
	models: string[];
	samples: number;
	maxTokens: number;
	json: boolean;
}

/** Split, trim, and validate `provider/id` refs; duplicates collapse, first occurrence keeps order. */
export function parseModelRefs(values: readonly string[]): string[] {
	const refs: string[] = [];
	for (const value of values) {
		for (const part of value.split(",")) {
			const ref = part.trim();
			if (ref === "") continue;
			if (!MODEL_REF.test(ref)) throw new UsageError(`model must be "provider/id", got: ${ref}`);
			if (!refs.includes(ref)) refs.push(ref);
		}
	}
	return refs;
}

function parseBoundedInt(flag: string, value: string | undefined, fallback: number, max: number): number {
	if (value === undefined) return fallback;
	if (!/^\d+$/.test(value)) throw new UsageError(`--${flag} must be an integer, got: ${value}`);
	const n = Number(value);
	if (n < 1 || n > max) throw new UsageError(`--${flag} must be within 1..${max}, got: ${value}`);
	return n;
}

/** Resolve shared probe flags. Model refs: `--model` > `CLSSCK_PROBE_MODELS`. */
export function resolveProbeSettings(
	values: ProbeCliValues,
	env: Record<string, string | undefined> = process.env,
	requireModels = true,
): ProbeSettings {
	const explicitModels = values.model;
	const models =
		explicitModels === undefined
			? parseModelRefs([env[PROBE_MODELS_ENV] ?? ""])
			: parseModelRefs(explicitModels);
	if (explicitModels !== undefined && models.length === 0) {
		throw new UsageError("--model was supplied but selected no models");
	}
	if (requireModels && models.length === 0) {
		throw new UsageError(`no models selected: pass --model <provider/id> or set ${PROBE_MODELS_ENV}`);
	}
	return {
		models,
		samples: parseBoundedInt("samples", values.samples, DEFAULT_SAMPLES, MAX_SAMPLES),
		maxTokens: parseBoundedInt("max-tokens", values["max-tokens"], DEFAULT_MAX_TOKENS, MAX_OUTPUT_TOKENS),
		json: values.json === true,
	};
}

/** Strict `parseArgs`: unknown flags, missing values, and positionals become UsageError. */
export function parseCli(args: string[], options: ParseArgsOptionsConfig): ProbeCliValues {
	try {
		// Pragmatic cast: `options` is declared by the caller from PROBE_FLAGS + its own flags.
		return parseArgs({ args, options, strict: true, allowPositionals: false }).values as ProbeCliValues;
	} catch (err) {
		throw new UsageError(err instanceof Error ? err.message : String(err));
	}
}

/** Print a UsageError with usage and exit 2; rethrow anything else. */
export function exitOnUsageError(err: unknown, usage: string): never {
	if (!(err instanceof UsageError)) throw err;
	console.error(`error: ${err.message}\n${usage}`);
	process.exit(2);
}

/**
 * Host packages are resolved from the caller's working directory (the OMP checkout or
 * install), so the specifier is runtime-selected and a static import cannot work.
 * Runs after argument validation so `--help` and usage errors never load the host.
 */
async function loadHost(): Promise<{
	completeSimple: typeof PiAi.completeSimple;
	getBundledModel: typeof PiCatalog.getBundledModel;
}> {
	const ai = (await import(Bun.resolveSync("@oh-my-pi/pi-ai", process.cwd()))) as typeof PiAi;
	const catalog = (await import(Bun.resolveSync("@oh-my-pi/pi-catalog/models", process.cwd()))) as typeof PiCatalog;
	return { completeSimple: ai.completeSimple, getBundledModel: catalog.getBundledModel };
}

function extractText(content: AssistantMessage["content"]): string {
	let out = "";
	for (const block of content) {
		if (block.type === "text") out += block.text;
	}
	return out.trim();
}

function buildUserPrompt(name: string, schema: unknown, template: string): string {
	const schemaText = typeof schema === "string" ? schema : JSON.stringify(schema, null, 2);
	return [
		`Tool name: ${name}`,
		"",
		"JSON parameter schema:",
		"```json",
		schemaText,
		"```",
		"",
		"Description outline to complete (write the body of every section; output ONLY the finished description):",
		"",
		template,
	].join("\n");
}

export async function probe(opts: ProbeOptions): Promise<ProbeRun> {
	const refs = parseModelRefs(opts.models ?? []);
	if (refs.length === 0) throw new UsageError("probe() requires at least one provider/id model ref");
	const sampleCount = parseBoundedInt(
		"samples",
		opts.samples === undefined ? undefined : String(opts.samples),
		DEFAULT_SAMPLES,
		MAX_SAMPLES,
	);
	const maxTokens = parseBoundedInt(
		"max-tokens",
		opts.maxTokens === undefined ? undefined : String(opts.maxTokens),
		DEFAULT_MAX_TOKENS,
		MAX_OUTPUT_TOKENS,
	);
	const name = opts.name ?? "the tool";
	const userPrompt = buildUserPrompt(name, opts.schema, opts.template);
	const { completeSimple, getBundledModel } = await loadHost();

	const resolveModel = (ref: string): Model<Api> => {
		const slash = ref.indexOf("/");
		// Runtime-validated: getBundledModel returns undefined for an unknown provider/id.
		const model = getBundledModel(ref.slice(0, slash) as GeneratedProvider, ref.slice(slash + 1));
		if (!model) throw new Error(`unknown model in host catalog: ${ref}`);
		return model;
	};

	const drawOne = async (model: Model<Api>): Promise<ProbeSample> => {
		try {
			const response = await completeSimple(
				model,
				{
					systemPrompt: [SYSTEM_PROMPT],
					messages: [{ role: "user", content: userPrompt, timestamp: Date.now() }],
				},
				{
					maxTokens,
					disableReasoning: true,
					signal: opts.signal,
				},
			);
			const text = extractText(response.content);
			const sample: ProbeSample = { text, stopReason: response.stopReason, usage: response.usage };
			if (response.stopReason === "error") sample.error = response.errorMessage ?? "unknown error";
			return sample;
		} catch (err) {
			return { text: "", stopReason: "error", error: err instanceof Error ? err.message : String(err) };
		}
	};

	const results = await Promise.all(
		refs.map(async (ref): Promise<ProbeModelResult> => {
			let model: Model<Api>;
			try {
				model = resolveModel(ref);
			} catch (err) {
				return { model: ref, samples: [{ text: "", stopReason: "error", error: err instanceof Error ? err.message : String(err) }] };
			}
			const samples = await Promise.all(Array.from({ length: sampleCount }, () => drawOne(model)));
			return { model: `${model.provider}/${model.id}`, samples };
		}),
	);

	return { prompt: userPrompt, results };
}

function formatUsage(usage: AssistantMessage["usage"] | undefined): string {
	if (!usage) return "";
	const out = typeof usage.output === "number" ? usage.output : undefined;
	return out === undefined ? "" : `, ${out} tok`;
}

/** Human-readable sample blocks, one section per model. */
export function printRun(run: ProbeRun): void {
	for (const result of run.results) {
		console.log(`\n############ ${result.model} ############`);
		result.samples.forEach((s, i) => {
			const tag = s.error ? `ERROR: ${s.error}` : `${s.stopReason}${formatUsage(s.usage)}`;
			console.log(`\n----- sample ${i + 1}/${result.samples.length} [${tag}] -----`);
			console.log(s.error ? "" : s.text);
		});
	}
}

async function resolveInput(value: string): Promise<string> {
	const file = Bun.file(value);
	if (await file.exists()) return (await file.text()).trim();
	return value;
}

async function main(): Promise<void> {
	let schemaArg: string;
	let templateArg: string;
	let name: string | undefined;
	let settings: ProbeSettings;
	try {
		const values = parseCli(Bun.argv.slice(2), {
			schema: { type: "string" },
			template: { type: "string" },
			name: { type: "string" },
			...PROBE_FLAGS,
		});
		if (values.help) {
			console.log(USAGE);
			return;
		}
		if (!values.schema || !values.template) throw new UsageError("--schema and --template are required");
		schemaArg = values.schema;
		templateArg = values.template;
		name = values.name;
		settings = resolveProbeSettings(values);
	} catch (err) {
		return exitOnUsageError(err, USAGE);
	}

	const schemaRaw = await resolveInput(schemaArg);
	let schema: unknown = schemaRaw;
	try {
		schema = JSON.parse(schemaRaw);
	} catch {
		// Leave as raw text — caller may pass a non-JSON schema notation.
	}
	const template = await resolveInput(templateArg);

	const run = await probe({
		schema,
		template,
		name,
		models: settings.models,
		samples: settings.samples,
		maxTokens: settings.maxTokens,
	});

	if (settings.json) {
		console.log(JSON.stringify(run, null, 2));
		return;
	}
	printRun(run);
}

if (import.meta.main) {
	await main();
}
