import { afterEach, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { copyShare } from "./CreateRoomDialog";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("copies via execCommand when navigator.clipboard is unavailable, and reports failure honestly", async () => {
  vi.stubGlobal("navigator", {});
  const success = vi.spyOn(toast, "success").mockImplementation(() => 1);
  const error = vi.spyOn(toast, "error").mockImplementation(() => 1);
  document.execCommand = vi.fn(() => true);
  await copyShare("r1");
  expect(success).toHaveBeenCalled();

  document.execCommand = vi.fn(() => false);
  await copyShare("r1");
  expect(String(error.mock.calls[0]?.[0])).toContain("/r/r1");
});
