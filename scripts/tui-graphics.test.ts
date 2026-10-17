import { afterEach, describe, expect, test } from "bun:test";
import { deflateSync } from "node:zlib";
import * as canvas from "@napi-rs/canvas";
import { Screen } from "../packs/clssck-development/tools/tui";

const screens: Screen[] = [];

afterEach(() => {
	for (const screen of screens.splice(0)) screen.dispose();
});

async function newScreen(): Promise<Screen> {
	const screen = await Screen.create(20, 5);
	screens.push(screen);
	// Hide the cursor overlay so only images add color to the screenshot.
	screen.feed(Buffer.from("\x1b[?25l"));
	return screen;
}

type Color = readonly [number, number, number];

const RED: Color = [255, 0, 0];
const GREEN: Color = [0, 255, 0];
const BLUE: Color = [0, 0, 255];
const YELLOW: Color = [255, 255, 0];

/** Solid RGBA pixels, `pixels` of them. */
function solid(color: Color, pixels: number): Buffer {
	return Buffer.alloc(pixels * 4).fill(Buffer.from([...color, 255]));
}

/** Writes one kitty-graphics escape; `keys` is the control data. */
function apc(screen: Screen, keys: string, payload: Buffer = Buffer.alloc(0)) {
	screen.feed(Buffer.from(`\x1b_G${keys};${payload.toString("base64")}\x1b\\`));
}

/** Moves to terminal column `column` of row 1, then transmits and places an image one cell wide. */
function show(screen: Screen, id: number, column: number, keys: string, payload: Buffer) {
	screen.feed(Buffer.from(`\x1b[1;${column + 1}H`));
	apc(screen, `a=T,i=${id},c=1,r=1,C=1,q=2,${keys}`, payload);
}

/** Whether any pixel of the screenshot is exactly `color`. */
async function rendered(screen: Screen, color: Color): Promise<boolean> {
	const image = await canvas.loadImage(await screen.png());
	const surface = canvas.createCanvas(image.width, image.height);
	const ctx = surface.getContext("2d");
	ctx.drawImage(image, 0, 0);
	const { data } = ctx.getImageData(0, 0, image.width, image.height);
	for (let i = 0; i < data.length; i += 4) {
		if (data[i] === color[0] && data[i + 1] === color[1] && data[i + 2] === color[2]) return true;
	}
	return false;
}

function pngOf(color: Color, width: number, height: number): Buffer {
	const surface = canvas.createCanvas(width, height);
	const ctx = surface.getContext("2d");
	ctx.fillStyle = `rgb(${color.join(",")})`;
	ctx.fillRect(0, 0, width, height);
	return surface.toBuffer("image/png");
}

/** Base64 characters per filler chunk: the largest multiple of four the terminal core delivers. */
const CHUNK_CHARS = 1048552;

describe("kitty graphics ordinary images", () => {
	test("RGBA, RGB, and PNG transmissions render", async () => {
		const screen = await newScreen();
		show(screen, 1, 0, "f=32,s=2,v=2", solid(RED, 4));
		show(screen, 2, 1, "f=24,s=2,v=2", Buffer.alloc(12).fill(Buffer.from(GREEN)));
		show(screen, 3, 2, "f=100", pngOf(BLUE, 4, 4));
		expect(await rendered(screen, RED)).toBe(true);
		expect(await rendered(screen, GREEN)).toBe(true);
		expect(await rendered(screen, BLUE)).toBe(true);
	});

	test("compressed and chunked transmissions render", async () => {
		const screen = await newScreen();
		show(screen, 1, 0, "f=32,s=2,v=2,o=z", deflateSync(solid(RED, 4)));
		expect(await rendered(screen, RED)).toBe(true);

		const pixels = solid(YELLOW, 4);
		show(screen, 2, 1, "f=32,s=2,v=2,m=1", pixels.subarray(0, 8));
		apc(screen, "m=0", pixels.subarray(8));
		expect(await rendered(screen, YELLOW)).toBe(true);
	});
});

describe("kitty graphics bounds", () => {
	test("a chunk stream past the transmission limit is dropped and the next image renders", async () => {
		const screen = await newScreen();
		screen.feed(Buffer.from("\x1b[1;1H"));
		// The leading pixel would render if the stream were accepted.
		apc(screen, "a=T,i=1,c=1,r=1,C=1,q=2,f=32,s=1,v=1,m=1", solid(RED, 1));
		// 90 filler chunks of ~768 KiB decoded exceed the 64 MiB transmission limit.
		const filler = "A".repeat(CHUNK_CHARS);
		for (let i = 0; i < 90; i++) screen.feed(Buffer.from(`\x1b_Gm=1;${filler}\x1b\\`));
		apc(screen, "m=0");
		expect(await rendered(screen, RED)).toBe(false);
		show(screen, 2, 1, "f=32,s=1,v=1", solid(GREEN, 1));
		expect(await rendered(screen, GREEN)).toBe(true);
	});

	test("too many tiny chunks are dropped without retaining per-chunk overhead", async () => {
		const screen = await newScreen();
		screen.feed(Buffer.from("\x1b[1;1H"));
		apc(screen, "a=T,i=1,c=1,r=1,C=1,q=2,f=32,s=1,v=1,m=1", solid(RED, 1));
		for (let i = 0; i < 40_000; i++) apc(screen, "m=1", Buffer.from([0, 0, 0]));
		apc(screen, "m=0");
		expect(await rendered(screen, RED)).toBe(false);
		show(screen, 2, 1, "f=32,s=1,v=1", solid(GREEN, 1));
		expect(await rendered(screen, GREEN)).toBe(true);
	});

	test("a chunk stream within the limit still assembles", async () => {
		const screen = await newScreen();
		show(screen, 1, 0, "f=32,s=1,v=1,m=1", solid(YELLOW, 1).subarray(0, 2));
		apc(screen, "m=0", solid(YELLOW, 1).subarray(2));
		expect(await rendered(screen, YELLOW)).toBe(true);
	});

	test("uncompressed raw payloads cannot exceed their declared size", async () => {
		const screen = await newScreen();
		show(screen, 1, 0, "f=32,s=1,v=1", Buffer.concat([solid(RED, 1), Buffer.alloc(512 * 1024)]));
		expect(await rendered(screen, RED)).toBe(false);
		show(screen, 2, 1, "f=32,s=1,v=1", solid(GREEN, 1));
		expect(await rendered(screen, GREEN)).toBe(true);
	});

	test("compressed payloads cannot expand past their declared size", async () => {
		const screen = await newScreen();
		// ~80 KiB on the wire, 80 MiB inflated: raw and PNG decompression bombs.
		const padding = Buffer.alloc(80 * 1024 * 1024);
		show(screen, 1, 0, "f=32,s=1,v=1,o=z", deflateSync(Buffer.concat([solid(RED, 1), padding])));
		show(screen, 2, 1, "f=100,o=z", deflateSync(Buffer.concat([pngOf(RED, 4, 4), padding])));
		// A small expansion past the declared 1x1 size is refused too.
		show(screen, 3, 2, "f=32,s=1,v=1,o=z", deflateSync(solid(RED, 1024)));
		expect(await rendered(screen, RED)).toBe(false);
		show(screen, 4, 3, "f=32,s=1,v=1,o=z", deflateSync(solid(BLUE, 1)));
		expect(await rendered(screen, BLUE)).toBe(true);
	});

	test("absurd or malformed declarations are dropped before decoding", async () => {
		const screen = await newScreen();
		// Declared dimensions past the per-side and area limits.
		show(screen, 1, 0, "f=32,s=100000,v=100000", solid(RED, 1));
		show(screen, 2, 1, "f=32,s=4097,v=4097", solid(RED, 1));
		// Declared size larger than the data supplied.
		show(screen, 3, 2, "f=32,s=2,v=2", solid(RED, 1));
		// Unsupported pixel format.
		show(screen, 4, 3, "f=16,s=1,v=1", solid(RED, 2));
		// PNG whose IHDR claims 100000x100000, and bytes that are not a PNG.
		const header = Buffer.from(pngOf(RED, 1, 1));
		header.writeUInt32BE(100000, 16);
		header.writeUInt32BE(100000, 20);
		show(screen, 5, 4, "f=100", header);
		show(screen, 6, 5, "f=100", solid(RED, 16));
		expect(await rendered(screen, RED)).toBe(false);
		show(screen, 7, 6, "f=32,s=1,v=1", solid(RED, 1));
		expect(await rendered(screen, RED)).toBe(true);
	});

	test("retained raw images are evicted oldest-first by stored and decoded bytes", async () => {
		const screen = await newScreen();
		// Five images each retain 16 MiB of source and may hold a 16 MiB RGBA raster; four fit the 128 MiB budget.
		const colors: Color[] = Array.from({ length: 5 }, (_, i) => [20 + i * 40, 200 - i * 10, 90]);
		for (const [i, color] of colors.entries()) {
			show(screen, i + 1, i, "f=32,s=2048,v=2048,o=z", deflateSync(solid(color, 2048 * 2048)));
		}
		expect(await rendered(screen, colors[0])).toBe(false);
		for (const color of colors.slice(1)) expect(await rendered(screen, color)).toBe(true);
	});

	test("highly compressed PNGs are budgeted by decoded size", async () => {
		const screen = await newScreen();
		const colors: Color[] = Array.from({ length: 8 }, (_, i) => [20 + i * 25, 200 - i * 10, 90]);
		for (const [i, color] of colors.entries()) show(screen, i + 1, i, "f=100", pngOf(color, 2048, 2048));
		expect(await rendered(screen, colors[0])).toBe(false);
		expect(await rendered(screen, colors.at(-1)!)).toBe(true);
	});

	test("retained images are evicted oldest-first by count", async () => {
		const screen = await newScreen();
		const pixel = solid(RED, 1);
		for (let id = 1; id <= 129; id++) apc(screen, `a=t,i=${id},q=2,f=32,s=1,v=1`, pixel);
		screen.feed(Buffer.from("\x1b[1;1H"));
		apc(screen, "a=p,i=1,c=1,r=1,C=1,q=2");
		expect(await rendered(screen, RED)).toBe(false);
		screen.feed(Buffer.from("\x1b[1;2H"));
		apc(screen, "a=p,i=129,c=1,r=1,C=1,q=2");
		expect(await rendered(screen, RED)).toBe(true);
	});
});
