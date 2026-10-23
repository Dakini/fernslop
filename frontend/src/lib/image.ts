// Shrinks large photos in the browser before they are uploaded or identified (#209), so a
// phone photo over the server's 5 MB limit still goes through, then refuses what the server
// would refuse (#211), so no request is sent for it. Browser APIs only.

/** The server's upload limit and messages (backend/app/uploads.py). */
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
export const UNSUPPORTED_TYPE_MESSAGE = "Please use a JPG, PNG or WebP image";
export const TOO_LARGE_MESSAGE = "That photo is over 5 MB";

/** Files of this size or smaller are sent as they are. */
export const RESIZE_OVER_BYTES = 1024 * 1024;
/** Longest side of a resized photo, in pixels. */
export const MAX_SIDE = 2048;
const JPEG_QUALITY = 0.85;
/** Enough of the file to find the dimensions, EXIF orientation and animation chunks. */
const HEADER_BYTES = 512 * 1024;

export type ImageInfo = {
  /** Displayed size, i.e. after the EXIF orientation is applied. */
  width: number;
  height: number;
  animated: boolean;
};

/** The image type the leading bytes say this is, or null; as the server's `sniff_image_type`. */
export function sniffImageType(bytes: Uint8Array): string | null {
  if (bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff)
    return "image/jpeg";
  if (PNG_SIGNATURE.every((v, i) => bytes[i] === v)) return "image/png";
  if (
    bytes.length >= 12 &&
    ascii(bytes, 0, 4) === "RIFF" &&
    ascii(bytes, 8, 4) === "WEBP"
  )
    return "image/webp";
  return null;
}

/**
 * The file as the server will take it, typed by its bytes rather than its name or `file.type`.
 * Throws an Error with the server's message for a file that is not a JPEG, PNG or WebP, whose
 * header is broken, or that is over 5 MB.
 */
export async function checkImage(file: File): Promise<File> {
  const header = await readBytes(file, HEADER_BYTES);
  const type = sniffImageType(header);
  // A file read whole whose header cannot be parsed is broken; a longer one is left to the server.
  const broken =
    type !== null && file.size <= HEADER_BYTES && !readImageInfo(header, type);
  if (!type || broken) throw new Error(UNSUPPORTED_TYPE_MESSAGE);
  if (file.size > MAX_UPLOAD_BYTES) throw new Error(TOO_LARGE_MESSAGE);
  return retyped(file, type);
}

/** Dimensions, orientation and animation read from the start of a JPEG, PNG or WebP; null if unreadable. */
export function readImageInfo(
  bytes: Uint8Array,
  type: string,
): ImageInfo | null {
  try {
    if (type === "image/jpeg") return readJpeg(bytes);
    if (type === "image/png") return readPng(bytes);
    if (type === "image/webp") return readWebp(bytes);
  } catch {
    // A truncated or odd header: treat as unreadable.
  }
  return null;
}

/** The size to resize to, or null when the file should be sent unchanged. */
export function resizeTarget(
  info: ImageInfo | null,
  fileSize: number,
): { width: number; height: number } | null {
  if (!info || info.animated || fileSize <= RESIZE_OVER_BYTES) return null;
  const longest = Math.max(info.width, info.height);
  if (longest <= MAX_SIDE) return null;
  const scale = MAX_SIDE / longest;
  return {
    width: Math.max(1, Math.round(info.width * scale)),
    height: Math.max(1, Math.round(info.height * scale)),
  };
}

/**
 * The file to upload, resized as `resizeImage` says and then checked by `checkImage`, which
 * throws for a file the server would refuse, so no request is sent for it.
 */
export async function prepareImage(file: File): Promise<File> {
  const type = sniffImageType(await readBytes(file, 12));
  // Typed by its bytes, so a PNG named .jpg resizes as a PNG; anything else is refused unread.
  return checkImage(type ? await resizeImage(retyped(file, type)) : file);
}

/** The first `n` bytes. FileReader where `Blob.arrayBuffer` is missing (older Safari, jsdom). */
function readBytes(file: Blob, n: number): Promise<Uint8Array> {
  const part = file.slice(0, n);
  if (typeof part.arrayBuffer === "function")
    return part.arrayBuffer().then((b) => new Uint8Array(b));
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(new Uint8Array(r.result as ArrayBuffer));
    r.onerror = () => reject(r.error);
    r.readAsArrayBuffer(part);
  });
}

function retyped(file: File, type: string): File {
  return file.type === type
    ? file
    : new File([file], file.name, { type, lastModified: file.lastModified });
}

/**
 * A still JPEG, PNG or WebP over 1 MB and over 2048 px is resized to 2048 px on its longest side
 * (JPEG stays JPEG; PNG stays PNG; WebP stays WebP where the browser can encode it, else an
 * opaque WebP becomes JPEG and one with transparency PNG). Anything else, anything the browser
 * cannot decode or encode, and any result that is not smaller comes back unchanged.
 */
async function resizeImage(file: File): Promise<File> {
  if (file.size <= RESIZE_OVER_BYTES || typeof createImageBitmap !== "function")
    return file;
  try {
    const header = await readBytes(file, HEADER_BYTES);
    const target = resizeTarget(readImageInfo(header, file.type), file.size);
    if (!target) return file;

    // Without WebP encoding, an opaque WebP falls back to JPEG (#218), one with alpha to PNG.
    const fallback =
      file.type === "image/webp" && !webpHasAlpha(header)
        ? "image/jpeg"
        : "image/png";
    const bitmap = await decode(file, target);
    let blob: Blob | null;
    try {
      blob = await encode(bitmap, target, file.type, fallback);
    } finally {
      bitmap.close();
    }
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], renamed(file.name, file.type, blob.type), {
      type: blob.type,
      lastModified: file.lastModified,
    });
  } catch {
    // Unsupported, out of memory, ...: send the original and let the server answer as before.
    return file;
  }
}

async function decode(
  file: File,
  target: { width: number; height: number },
): Promise<ImageBitmap> {
  try {
    // Decoding straight to the target size spares memory where the browser supports it.
    return await createImageBitmap(file, {
      imageOrientation: "from-image",
      resizeWidth: target.width,
      resizeHeight: target.height,
      resizeQuality: "high",
    });
  } catch {
    return await createImageBitmap(file, { imageOrientation: "from-image" });
  }
}

async function encode(
  bitmap: ImageBitmap,
  target: { width: number; height: number },
  type: string,
  fallback: string,
): Promise<Blob | null> {
  const canvas = document.createElement("canvas");
  canvas.width = target.width;
  canvas.height = target.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(bitmap, 0, 0, target.width, target.height);
  const toBlob = (t: string, q?: number) =>
    new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, t, q));
  try {
    const quality = (t: string) =>
      t === "image/jpeg" ? JPEG_QUALITY : undefined;
    const blob = await toBlob(type, quality(type));
    // A browser that cannot encode WebP returns PNG; re-encode as the fallback type.
    return (
      blob &&
      (blob.type === type ? blob : await toBlob(fallback, quality(fallback)))
    );
  } finally {
    canvas.width = canvas.height = 0; // free the pixels now rather than at the next GC
  }
}

function renamed(name: string, from: string, to: string): string {
  if (from === to) return name;
  const ext =
    to === "image/png" ? ".png" : to === "image/webp" ? ".webp" : ".jpg";
  return name.replace(/\.[^.]*$/, "") + ext;
}

// --- Header parsing ----------------------------------------------------------

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const u16be = (b: Uint8Array, i: number) => (b[i]! << 8) | b[i + 1]!;
const u32be = (b: Uint8Array, i: number) =>
  ((b[i]! << 24) | (b[i + 1]! << 16) | (b[i + 2]! << 8) | b[i + 3]!) >>> 0;
const u16le = (b: Uint8Array, i: number) => b[i]! | (b[i + 1]! << 8);
const u24le = (b: Uint8Array, i: number) =>
  b[i]! | (b[i + 1]! << 8) | (b[i + 2]! << 16);
const u32le = (b: Uint8Array, i: number) =>
  (u24le(b, i) | (b[i + 3]! << 24)) >>> 0;
const ascii = (b: Uint8Array, i: number, n: number) =>
  String.fromCharCode(...b.subarray(i, i + n));

function readPng(b: Uint8Array): ImageInfo | null {
  if (u32be(b, 0) !== 0x89504e47 || ascii(b, 12, 4) !== "IHDR") return null;
  const width = u32be(b, 16);
  const height = u32be(b, 20);
  // An APNG's acTL chunk must come before the first IDAT.
  let animated = false;
  for (let i = 8; i + 8 <= b.length;) {
    const type = ascii(b, i + 4, 4);
    if (type === "acTL") animated = true;
    if (type === "acTL" || type === "IDAT") break;
    i += 12 + u32be(b, i);
  }
  return { width, height, animated };
}

function readWebp(b: Uint8Array): ImageInfo | null {
  if (ascii(b, 0, 4) !== "RIFF" || ascii(b, 8, 4) !== "WEBP") return null;
  let size: { width: number; height: number } | null = null;
  let animated = false;
  for (let i = 12; i + 8 <= b.length;) {
    const fourcc = ascii(b, i, 4);
    const d = i + 8;
    if (fourcc === "VP8X") {
      animated ||= (b[d]! & 0x02) !== 0;
      size = { width: u24le(b, d + 4) + 1, height: u24le(b, d + 7) + 1 };
    } else if (fourcc === "ANIM" || fourcc === "ANMF") {
      animated = true;
    } else if (fourcc === "VP8 " && !size) {
      size = {
        width: u16le(b, d + 6) & 0x3fff,
        height: u16le(b, d + 8) & 0x3fff,
      };
    } else if (fourcc === "VP8L" && !size) {
      const bits = u32le(b, d + 1);
      size = {
        width: (bits & 0x3fff) + 1,
        height: ((bits >>> 14) & 0x3fff) + 1,
      };
    }
    if (fourcc === "VP8 " || fourcc === "VP8L" || animated) break;
    const len = u32le(b, i + 4);
    i = d + len + (len & 1);
  }
  return size && { ...size, animated };
}

/**
 * Whether a WebP header says the image has transparency: the VP8X alpha flag, or the VP8L
 * alpha_is_used bit. A plain lossy VP8 image has none. Read from the header, not the pixels.
 */
export function webpHasAlpha(b: Uint8Array): boolean {
  if (ascii(b, 0, 4) !== "RIFF" || ascii(b, 8, 4) !== "WEBP") return false;
  const fourcc = ascii(b, 12, 4);
  if (fourcc === "VP8X") return (b[20]! & 0x10) !== 0;
  // VP8L: signature byte, then 14-bit width, 14-bit height and the alpha bit.
  if (fourcc === "VP8L") return ((u32le(b, 21) >>> 28) & 1) !== 0;
  return false;
}

function readJpeg(b: Uint8Array): ImageInfo | null {
  if (u16be(b, 0) !== 0xffd8) return null;
  let orientation = 1;
  for (let i = 2; i + 4 <= b.length;) {
    if (b[i] !== 0xff) return null;
    const marker = b[i + 1]!;
    if (marker === 0xff) {
      i += 1;
      continue;
    }
    const len = u16be(b, i + 2);
    if (marker === 0xe1 && ascii(b, i + 4, 6) === "Exif\0\0")
      orientation = exifOrientation(b, i + 10) ?? orientation;
    // SOF0..SOF15, except DHT (C4), JPG (C8) and DAC (CC).
    if (
      marker >= 0xc0 &&
      marker <= 0xcf &&
      marker !== 0xc4 &&
      marker !== 0xc8 &&
      marker !== 0xcc
    ) {
      const height = u16be(b, i + 5);
      const width = u16be(b, i + 7);
      // Orientations 5-8 rotate by 90 degrees, so the displayed width is the stored height.
      return orientation >= 5
        ? { width: height, height: width, animated: false }
        : { width, height, animated: false };
    }
    if (marker === 0xda) return null;
    i += 2 + len;
  }
  return null;
}

function exifOrientation(b: Uint8Array, tiff: number): number | null {
  const le = ascii(b, tiff, 2) === "II";
  const r16 = (i: number) => (le ? u16le(b, i) : u16be(b, i));
  const r32 = (i: number) => (le ? u32le(b, i) : u32be(b, i));
  const ifd = tiff + r32(tiff + 4);
  const count = r16(ifd);
  for (let n = 0; n < count; n++) {
    const entry = ifd + 2 + n * 12;
    if (r16(entry) === 0x0112) return r16(entry + 8);
  }
  return null;
}
