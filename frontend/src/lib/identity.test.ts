import { afterEach, expect, it, vi } from "vitest";
import { loadIdentity } from "./identity";

afterEach(() => {
  vi.unstubAllGlobals();
});

it("creates a UUID device id when crypto.randomUUID is missing (plain-http origin)", () => {
  vi.stubGlobal("crypto", { getRandomValues: (a: Uint8Array) => a.fill(7) });
  expect(loadIdentity().device_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});
