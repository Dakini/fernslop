// HTTP implementation of GardenService against the backend described in /openapi.yaml.
import type {
  Actor,
  FeedEvent,
  GardenService,
  Photo,
  RoomState,
} from "../types";

const GENERIC_ERROR = "Something went wrong. Please try again.";
const NETWORK_ERROR =
  "Couldn't reach the server. Check your connection and try again.";

export function createHttpService(
  opts: { baseUrl?: string } = {},
): GardenService {
  const base = (opts.baseUrl || "/api").replace(/\/+$/, "");
  const absolute = /^https?:\/\//i.test(base);

  /** `/api/photos/{id}` -> `https://host/api/photos/{id}` when the base is absolute, so <img> loads from the API host. */
  const origin = absolute ? new URL(base).origin : "";
  const photoUrl = (url: string): string =>
    absolute && url.startsWith("/") ? origin + url : url;
  const fixEvent = (e: FeedEvent): FeedEvent =>
    e.photo_url ? { ...e, photo_url: photoUrl(e.photo_url) } : e;

  function actorHeaders(actor: Actor): Record<string, string> {
    return {
      "X-Device-Id": actor.device_id,
      "X-Actor-Name": encodeURIComponent(actor.name),
    };
  }

  async function send(path: string, init: RequestInit = {}): Promise<Response> {
    let res: Response;
    try {
      res = await fetch(base + path, init);
    } catch {
      throw new Error(NETWORK_ERROR);
    }
    return res;
  }

  async function errorFrom(res: Response): Promise<Error> {
    try {
      const body = await res.json();
      if (body && typeof body.message === "string" && body.message)
        return new Error(body.message);
    } catch {
      /* non-JSON body */
    }
    return new Error(GENERIC_ERROR);
  }

  async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await send(path, init);
    if (!res.ok) throw await errorFrom(res);
    if (res.status === 204) return undefined as T;
    try {
      return (await res.json()) as T;
    } catch {
      throw new Error(GENERIC_ERROR);
    }
  }

  const body = (
    method: string,
    data: unknown,
    headers: Record<string, string> = {},
  ): RequestInit => ({
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(data),
  });

  const upload = (file: File): RequestInit => {
    const form = new FormData();
    form.append("file", file);
    return { method: "POST", body: form };
  };

  return {
    listRooms: () => json("/rooms"),
    createRoom: (input) => json("/rooms", body("POST", input)),
    async getRoomState(roomId) {
      const res = await send(`/rooms/${encodeURIComponent(roomId)}`);
      if (res.status === 404) return null;
      if (!res.ok) throw await errorFrom(res);
      let state: RoomState;
      try {
        state = await res.json();
      } catch {
        throw new Error(GENERIC_ERROR);
      }
      return { ...state, feed: state.feed.map(fixEvent) };
    },
    async deleteRoom(roomId) {
      const res = await send(`/rooms/${encodeURIComponent(roomId)}`, { method: "DELETE" });
      if (res.status === 404) return false;
      if (!res.ok) throw await errorFrom(res);
      return true;
    },

    listPlants: () => json("/plants"),
    searchPlants: (query) =>
      json(`/plants/search?q=${encodeURIComponent(query)}`),
    identifyPlant: (file) => json("/plants/identify", upload(file)),

    addPlant: (roomId, plantId, actor) =>
      json(
        `/rooms/${encodeURIComponent(roomId)}/plants`,
        body("POST", { plant_id: plantId }, actorHeaders(actor)),
      ),
    movePlant: (id, x, y, actor) =>
      json(
        `/room-plants/${encodeURIComponent(id)}`,
        body("PATCH", { x_pct: x, y_pct: y }, actorHeaders(actor)),
      ),
    removePlant: (id, actor) =>
      json(`/room-plants/${encodeURIComponent(id)}`, {
        method: "DELETE",
        headers: actorHeaders(actor),
      }),
    markCare: (id, care, actor) =>
      json(
        `/room-plants/${encodeURIComponent(id)}/care`,
        body("POST", { care }, actorHeaders(actor)),
      ),

    addArea: (roomId, input, actor) =>
      json(
        `/rooms/${encodeURIComponent(roomId)}/areas`,
        body("POST", input, actorHeaders(actor)),
      ),
    updateArea: (id, patch, actor) =>
      json(
        `/areas/${encodeURIComponent(id)}`,
        body("PATCH", patch, actorHeaders(actor)),
      ),
    deleteArea: (id, actor) =>
      json(`/areas/${encodeURIComponent(id)}`, {
        method: "DELETE",
        headers: actorHeaders(actor),
      }),

    async uploadPhoto(file) {
      const photo = await json<Photo>("/photos", upload(file));
      return { ...photo, url: photoUrl(photo.url) };
    },
    async postUpdate(roomId, text, photoId, actor) {
      const ev = await json<FeedEvent>(
        `/rooms/${encodeURIComponent(roomId)}/posts`,
        body("POST", { text, photo_id: photoId }, actorHeaders(actor)),
      );
      return fixEvent(ev);
    },
    undoEvent: (eventId, actor) =>
      json(`/feed-events/${encodeURIComponent(eventId)}/undo`, {
        method: "POST",
        headers: actorHeaders(actor),
      }),

    followRoom: (roomId, email) =>
      json(
        `/rooms/${encodeURIComponent(roomId)}/follows`,
        body("POST", { email }),
      ),
    async unfollow(token) {
      const r = await json<{ unsubscribed: boolean }>(
        "/follows/unsubscribe",
        body("POST", { token }),
      );
      return r.unsubscribed;
    },

    subscribe(roomId, onChange) {
      const es = new EventSource(
        `${base}/rooms/${encodeURIComponent(roomId)}/live`,
      );
      es.addEventListener("change", () => onChange());
      return () => es.close();
    },
  };
}
