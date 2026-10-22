// The ONLY entry point the UI uses for backend calls.
// Swap `createMockService` for a real implementation of GardenService later.
import { createMockService, localStorageAdapter, memoryStorage } from "./mock/mockService";
import type { GardenService } from "./types";

let instance: GardenService | null = null;

export function getServices(): GardenService {
  if (!instance) {
    const browser = typeof window !== "undefined";
    instance = createMockService({
      storage: browser ? localStorageAdapter() : memoryStorage(),
      latencyMs: browser ? 120 : 0,
      broadcast: browser,
    });
  }
  return instance;
}

/** Test hook: inject a custom implementation. */
export function setServices(s: GardenService | null) {
  instance = s;
}

export * from "./types";
