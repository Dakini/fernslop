import { expect, it } from "vitest";
import {
  prepareImage,
  readImageInfo,
  resizeTarget,
  webpHasAlpha,
} from "./image";

const MB = 1024 * 1024;

// Minimal file headers: just the bytes readImageInfo looks at.
function png(
  width: number,
  height: number,
  chunks: string[],
): Uint8Array<ArrayBuffer> {
  const out = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  const be32 = (n: number) => [
    n >>> 24,
    (n >>> 16) & 255,
    (n >>> 8) & 255,
    n & 255,
  ];
  const chunk = (type: string, data: number[]) =>
    out.push(
      ...be32(data.length),
      ...[...type].map((c) => c.charCodeAt(0)),
      ...data,
      0,
      0,
      0,
      0,
    );
  chunk("IHDR", [...be32(width), ...be32(height), 8, 6, 0, 0, 0]);
  for (const type of chunks)
    chunk(type, type === "acTL" ? [0, 0, 0, 2, 0, 0, 0, 0] : [0]);
  return new Uint8Array(out);
}

const le24 = (n: number) => [n & 255, (n >>> 8) & 255, (n >>> 16) & 255];

function webp(fourcc: string, data: number[]): Uint8Array {
  const chars = (s: string) => [...s].map((c) => c.charCodeAt(0));
  return new Uint8Array([
    ...chars("RIFF"),
    0,
    0,
    0,
    0,
    ...chars("WEBP" + fourcc),
    data.length,
    0,
    0,
    0,
    ...data,
  ]);
}

function animatedWebp(width: number, height: number): Uint8Array {
  // flags: animation
  return webp("VP8X", [0x02, 0, 0, 0, ...le24(width - 1), ...le24(height - 1)]);
}

/** A lossless VP8L header: signature, 14-bit width and height - 1, then the alpha bit. */
function losslessWebp(
  width: number,
  height: number,
  alpha: boolean,
): Uint8Array {
  const bits =
    ((width - 1) | ((height - 1) << 14) | (alpha ? 1 << 28 : 0)) >>> 0;
  return webp("VP8L", [0x2f, ...le24(bits), bits >>> 24]);
}

it("resizes a large still image to 2048 px on its longest side and keeps small or already small images", () => {
  const still = readImageInfo(png(4000, 3000, ["IDAT"]), "image/png");

  expect(still).toEqual({ width: 4000, height: 3000, animated: false });
  expect(resizeTarget(still, 6 * MB)).toEqual({ width: 2048, height: 1536 });
  expect(resizeTarget(still, MB)).toBeNull(); // 1 MB or less: sent as is
  expect(
    resizeTarget({ width: 2048, height: 1000, animated: false }, 4 * MB),
  ).toBeNull(); // already 2048 px
});

it("refuses HEIC bytes named .jpg and accepts a real PNG, typed by its bytes", async () => {
  // An iPhone HEIC starts with an ISO-BMFF "ftypheic" box, whatever it is named.
  const heic = new Uint8Array([
    0, 0, 0, 24, 102, 116, 121, 112, 104, 101, 105, 99,
  ]); // ....ftypheic
  await expect(
    prepareImage(new File([heic], "leaf.jpg", { type: "image/jpeg" })),
  ).rejects.toThrow("Please use a JPG, PNG or WebP image");

  const ok = await prepareImage(
    new File([png(1, 1, ["IDAT"])], "leaf.jpg", { type: "image/jpeg" }),
  );
  expect(ok.type).toBe("image/png");
});

it("never resizes an animated PNG or WebP", () => {
  const apng = readImageInfo(png(4000, 3000, ["acTL", "IDAT"]), "image/png");
  const awebp = readImageInfo(animatedWebp(4000, 3000), "image/webp");

  expect(apng?.animated).toBe(true);
  expect(awebp).toEqual({ width: 4000, height: 3000, animated: true });
  expect(resizeTarget(apng, 6 * MB)).toBeNull();
  expect(resizeTarget(awebp, 6 * MB)).toBeNull();
});

// --- WebP transparency (#218): an opaque WebP may fall back to JPEG, one with alpha to PNG ---

it("reads an opaque lossy, lossless or extended WebP header as having no alpha", () => {
  const lossy = webp("VP8 ", [0, 0, 0, 0x9d, 0x01, 0x2a, ...le24(4000), 0]);

  expect(webpHasAlpha(lossy)).toBe(false);
  expect(webpHasAlpha(losslessWebp(4000, 3000, false))).toBe(false);
  expect(webpHasAlpha(animatedWebp(4000, 3000))).toBe(false); // VP8X without the alpha flag
});

it("reads the VP8X alpha flag and the VP8L alpha bit as having alpha", () => {
  const extended = webp("VP8X", [0x10, 0, 0, 0, ...le24(3999), ...le24(2999)]);
  const lossless = losslessWebp(4000, 3000, true);

  expect(webpHasAlpha(extended)).toBe(true);
  expect(webpHasAlpha(lossless)).toBe(true);
  expect(readImageInfo(lossless, "image/webp")).toEqual({
    width: 4000,
    height: 3000,
    animated: false,
  });
});
