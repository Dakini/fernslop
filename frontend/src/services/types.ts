// Domain types + the single GardenService contract every backend call goes through.

export type PlantCategory = "flower" | "vegetable" | "herb" | "houseplant" | "shrub" | "tree";
export type CareType = "water" | "feed" | "prune" | "harvest";
export const CARE_TYPES: CareType[] = ["water", "feed", "prune", "harvest"];

export interface Plant {
  id: string;
  common_name: string;
  scientific_name: string;
  category: PlantCategory;
  description: string;
  image_url: string | null;
  water_every_days: number | null;
  feed_every_days: number | null;
  prune_every_days: number | null;
  harvest_every_days: number | null;
  source: string;
  source_url: string;
}

/** Live (not soft-deleted) rows allowed per room. The backend must enforce these. */
export const ROOM_LIMITS = { plants: 50, areas: 10 } as const;

export interface Room {
  /** UUID; also the room's public URL segment (`/r/{id}`). */
  id: string;
  name: string;
  description: string;
  region: string;
  created_at: string;
  last_activity_at: string;
}

export interface RoomPlant {
  id: string;
  room_id: string;
  plant_id: string;
  nickname: string | null;
  x_pct: number;
  y_pct: number;
  last_watered_at: string | null;
  last_fed_at: string | null;
  last_pruned_at: string | null;
  last_harvested_at: string | null;
  added_by_name: string;
  created_at: string;
  deleted_at: string | null;
}

export type AreaShape = "rect" | "ellipse";
export interface RoomArea {
  id: string;
  room_id: string;
  label: string;
  shape: AreaShape;
  x_pct: number;
  y_pct: number;
  w_pct: number;
  h_pct: number;
  colour: string;
  deleted_at: string | null;
}

export type FeedEventType =
  | "plant_added"
  | "plant_removed"
  | "plant_moved"
  | "care_done"
  | "area_changed"
  | "post";

export type UndoPayload =
  | { kind: "restore_plant"; room_plant: RoomPlant }
  | { kind: "delete_plant"; room_plant_id: string }
  | { kind: "restore_area"; area: RoomArea | null; area_id: string };

export interface FeedEvent {
  id: string;
  room_id: string;
  type: FeedEventType;
  actor_name: string;
  device_id: string;
  room_plant_id: string | null;
  text: string;
  photo_url: string | null;
  undo_payload: UndoPayload | null;
  undone_at: string | null;
  created_at: string;
}

/**
 * The answer to a follow request: only what was sent, so it never reveals an earlier follow.
 * The follow's token is never returned to the browser; it only goes out in emails.
 */
export interface RoomFollow {
  room_id: string;
  email: string;
}

export interface Photo {
  id: string;
  url: string;
}

export interface Actor {
  name: string;
  device_id: string;
}

export interface RoomSummary {
  room: Room;
  plants: { x_pct: number; y_pct: number; category: PlantCategory }[];
  areas: RoomArea[];
}

/** One page of the index; `next` is the `before` cursor for the following page, null on the last. */
export interface RoomPage {
  rooms: RoomSummary[];
  next: string | null;
}

export interface RoomState {
  room: Room;
  plants: RoomPlant[];
  areas: RoomArea[];
  feed: FeedEvent[];
}

export interface IdentifyCandidate {
  plant: Plant;
  confidence: number;
}

export type AreaInput = Pick<RoomArea, "label" | "shape" | "x_pct" | "y_pct" | "w_pct" | "h_pct" | "colour">;

export interface GardenService {
  /** Newest activity first, `limit` (default 30, at most 100) rooms per page; pass a page's `next` as `before`. */
  listRooms(page?: { before?: string | null; limit?: number }): Promise<RoomPage>;
  createRoom(input: { name: string; description?: string; region?: string }): Promise<Room>;
  getRoomState(roomId: string): Promise<RoomState | null>;
  /**
   * Permanently deletes a garden and everything in it. Idempotent: deleting a garden that is
   * already gone also succeeds and resolves true (the server answers 204 either way). False only
   * when an older server answers 404; callers treat both as "the garden is gone". Other errors reject.
   */
  deleteRoom(roomId: string): Promise<boolean>;

  listPlants(): Promise<Plant[]>;
  /** At most 12 matches, in reference order. */
  searchPlants(query: string): Promise<Plant[]>;
  identifyPlant(file: File): Promise<IdentifyCandidate[]>;

  addPlant(roomId: string, plantId: string, actor: Actor): Promise<RoomPlant>;
  movePlant(roomPlantId: string, x: number, y: number, actor: Actor): Promise<RoomPlant>;
  removePlant(roomPlantId: string, actor: Actor): Promise<void>;
  markCare(roomPlantId: string, care: CareType, actor: Actor): Promise<RoomPlant>;

  addArea(roomId: string, input: AreaInput, actor: Actor): Promise<RoomArea>;
  updateArea(areaId: string, patch: Partial<AreaInput>, actor: Actor): Promise<RoomArea>;
  deleteArea(areaId: string, actor: Actor): Promise<void>;

  /** Stores a JPEG/PNG/WebP photo (max 5 MB) for use in a post. */
  uploadPhoto(file: File): Promise<Photo>;
  postUpdate(roomId: string, text: string, photoId: string | null, actor: Actor): Promise<FeedEvent>;
  undoEvent(eventId: string, actor: Actor): Promise<void>;

  /** Stores an unconfirmed follow and emails a confirmation link; digests start once it is confirmed. */
  followRoom(roomId: string, email: string): Promise<RoomFollow>;
  /** True once the follow is confirmed (also on a repeat); false for an unknown or expired token. */
  confirmFollow(token: string): Promise<boolean>;
  unfollow(token: string): Promise<boolean>;

  /** Live updates for a room. Returns an unsubscribe function. */
  subscribe(roomId: string, onChange: () => void): () => void;
}
