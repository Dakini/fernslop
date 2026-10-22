import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { loadIdentity, nicknameError, saveNickname } from "./identity";

const KEY = "fernslop:identity";

// Node's own experimental `localStorage` global can shadow jsdom's, so each test gets a plain in-memory one.
beforeEach(() => {
  const items = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => items.get(k) ?? null,
    setItem: (k: string, v: string) => void items.set(k, v),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it("creates a UUID device id when crypto.randomUUID is missing (plain-http origin)", () => {
  vi.stubGlobal("crypto", { getRandomValues: (a: Uint8Array) => a.fill(7) });
  expect(loadIdentity().device_id).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
});

it("repairs a broken stored identity, keeping the valid half and saving the result", () => {
  localStorage.setItem(
    KEY,
    JSON.stringify({ device_id: "x".repeat(65), name: "Zoë" }),
  );
  const keptName = loadIdentity();
  localStorage.setItem(
    KEY,
    JSON.stringify({ device_id: "dev-1", name: "\u202eevil" }),
  );
  const keptDevice = loadIdentity();
  localStorage.setItem(KEY, "not json");
  const fresh = loadIdentity();

  expect(keptName.name).toBe("Zoë");
  expect(keptName.device_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(keptDevice).toEqual({
    device_id: "dev-1",
    name: expect.stringMatching(/^Anonymous /),
  });
  expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual(fresh);
  expect(fresh.device_id && fresh.name).toBeTruthy();
});

it("rejects a nickname with a control or format character or over 40 characters and does not save it", () => {
  const before = loadIdentity();

  const results = ["line\nbreak", "\u202eevil", "a".repeat(41)].map(
    (bad) => [nicknameError(bad), saveNickname(bad)] as const,
  );

  for (const [error, actor] of results) {
    expect(error).not.toBeNull();
    expect(actor).toEqual(before);
  }
  expect(loadIdentity()).toEqual(before);
});

it("accepts emoji nicknames counted by code point and keeps them whole", () => {
  for (const emoji of ["👩‍🌾", "🌱".repeat(40)]) {
    expect(nicknameError(emoji)).toBeNull();

    const actor = saveNickname(emoji);

    expect(actor.name).toBe(emoji);
    expect(() => encodeURIComponent(actor.name)).not.toThrow();
  }
});
