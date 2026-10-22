import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { createHttpService } from "./httpService";
import { getServices, setServices } from "../index";

const actor = { name: "Zoë 🌿", device_id: "dev-1" };
const reply = (status: number, body?: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  setServices(null);
});

describe("http GardenService", () => {
  it("uses the HTTP service by default and the mock when VITE_USE_MOCK=true", async () => {
    vi.stubEnv("VITE_USE_MOCK", "true");
    await getServices().listPlants();
    expect(fetchMock).not.toHaveBeenCalled();

    setServices(null);
    vi.stubEnv("VITE_USE_MOCK", "");
    vi.stubEnv("VITE_API_BASE_URL", "http://api.test/api/");
    fetchMock.mockResolvedValue(reply(200, []));
    await getServices().listPlants();
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/plants");
  });

  it("calls the documented path, verb and body, with encoded actor headers only for actors", async () => {
    const svc = createHttpService();
    fetchMock.mockResolvedValue(reply(200, []));
    await svc.searchPlants("rose & lily");
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/plants/search?q=rose%20%26%20lily",
    );

    fetchMock.mockResolvedValue(reply(201, { id: "rp1" }));
    await svc.addPlant("room1", "plant1", actor);
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/rooms/room1/plants");
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"plant_id":"plant1"}');
    expect(init.headers["X-Device-Id"]).toBe("dev-1");
    expect(init.headers["X-Actor-Name"]).toBe(encodeURIComponent("Zoë 🌿"));

    fetchMock.mockResolvedValue(reply(201, { id: "r1" }));
    await svc.createRoom({ name: "Mine" });
    expect(fetchMock.mock.calls[2][1].headers["X-Actor-Name"]).toBeUndefined();
  });

  it("maps results like the mock: void on 204, null on 404, unsubscribed flag, absolute photo urls", async () => {
    const svc = createHttpService({ baseUrl: "http://api.test/api" });
    fetchMock.mockResolvedValueOnce(reply(204));
    await expect(svc.removePlant("rp1", actor)).resolves.toBeUndefined();

    fetchMock.mockResolvedValueOnce(reply(404, { message: "Room not found" }));
    await expect(svc.getRoomState("nope")).resolves.toBeNull();

    fetchMock.mockResolvedValueOnce(reply(200, { unsubscribed: false }));
    await expect(svc.unfollow("tok")).resolves.toBe(false);

    fetchMock.mockResolvedValueOnce(
      reply(201, { id: "p1", url: "/api/photos/p1" }),
    );
    const photo = await svc.uploadPhoto(
      new File(["x"], "a.png", { type: "image/png" }),
    );
    expect(photo.url).toBe("http://api.test/api/photos/p1");
    expect(fetchMock.mock.calls[3][1].body).toBeInstanceOf(FormData);
  });

  it("rejects with the body message, or a generic message for network/non-JSON failures", async () => {
    const svc = createHttpService();
    fetchMock.mockResolvedValueOnce(reply(409, { message: "Room is full" }));
    await expect(svc.addPlant("r", "p", actor)).rejects.toThrow("Room is full");

    fetchMock.mockResolvedValueOnce(
      new Response("<html>Bad gateway</html>", { status: 502 }),
    );
    await expect(svc.listRooms()).rejects.toThrow(/\S/);

    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(svc.listRooms()).rejects.toThrow(/Couldn't reach the server/);
  });

  it("on 429 shows one friendly toast using Retry-After and rejects with the same message", async () => {
    const svc = createHttpService();
    const toastError = vi.spyOn(toast, "error");
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ message: "x" }), {
        status: 429,
        headers: { "Retry-After": "30" },
      }),
    );

    await expect(svc.movePlant("rp1", 1, 2, actor)).rejects.toThrow(
      "You're going a bit fast. Try again in 30 seconds.",
    );
    expect(toastError).toHaveBeenCalledWith(
      "You're going a bit fast. Try again in 30 seconds.",
      { id: "rate-limit" },
    );
    toastError.mockRestore();
  });

  it("subscribe opens an EventSource, fires onChange per change event only, and closes", () => {
    const listeners: Record<string, () => void> = {};
    const close = vi.fn();
    const ctor = vi.fn(function () {
      return {
        addEventListener: (t: string, fn: () => void) => (listeners[t] = fn),
        close,
      };
    });
    vi.stubGlobal("EventSource", ctor);
    const onChange = vi.fn();
    const stop = createHttpService().subscribe("room1", onChange);
    expect(ctor).toHaveBeenCalledWith("/api/rooms/room1/live");
    expect(Object.keys(listeners)).toEqual(["change"]); // pings are comments, never a listener
    listeners.change();
    expect(onChange).toHaveBeenCalledTimes(1);
    stop();
    expect(close).toHaveBeenCalled();
  });

  it("deleteRoom sends DELETE without actor headers: true on 204 (also when already gone), false on an old server's 404, rejects otherwise", async () => {
    const svc = createHttpService();
    fetchMock.mockResolvedValueOnce(reply(204));
    await expect(svc.deleteRoom("room 1")).resolves.toBe(true);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/rooms/room%201");
    expect(init.method).toBe("DELETE");
    expect(init.headers).toBeUndefined();

    fetchMock.mockResolvedValueOnce(reply(404, { message: "Room not found" }));
    await expect(svc.deleteRoom("room1")).resolves.toBe(false);

    fetchMock.mockResolvedValueOnce(reply(500, { message: "Boom" }));
    await expect(svc.deleteRoom("room1")).rejects.toThrow("Boom");
  });
});
