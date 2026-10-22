// The ONLY entry point the UI uses for backend calls.
// The HTTP service is the default (base URL from `VITE_API_BASE_URL`, default
// `/api`); `VITE_USE_MOCK=true` selects the in-browser mock.
import { createHttpService } from "./http/httpService";
import {
  createMockService,
  localStorageAdapter,
  memoryStorage,
} from "./mock/mockService";
import type { GardenService } from "./types";

let instance: GardenService | null = null;

export function getServices(): GardenService {
  if (!instance) {
    if (import.meta.env.VITE_USE_MOCK !== "true") {
      instance = createHttpService({
        baseUrl: import.meta.env.VITE_API_BASE_URL,
      });
      return instance;
    }
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
