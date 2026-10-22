import type { CareType, Plant, RoomPlant } from "./types";

const DAY = 86_400_000;

export const CARE_FIELDS: Record<CareType, { interval: keyof Plant; last: keyof RoomPlant }> = {
  water: { interval: "water_every_days", last: "last_watered_at" },
  feed: { interval: "feed_every_days", last: "last_fed_at" },
  prune: { interval: "prune_every_days", last: "last_pruned_at" },
  harvest: { interval: "harvest_every_days", last: "last_harvested_at" },
};

export const CARE_LABELS: Record<CareType, { verb: string; done: string; overdue: (n: string) => string }> = {
  water: { verb: "Mark watered", done: "watered", overdue: (n) => `${n} would love a drink` },
  feed: { verb: "Mark fed", done: "fed", overdue: (n) => `${n} is hungry for a feed` },
  prune: { verb: "Mark pruned", done: "pruned", overdue: (n) => `${n} could use a little trim` },
  harvest: { verb: "Mark harvested", done: "harvested", overdue: (n) => `${n} is ready to pick` },
};

export interface CareStatus {
  care: CareType;
  intervalDays: number;
  daysLeft: number; // may be negative when overdue
  fraction: number; // 0..1 remaining
  overdue: boolean;
  dueAt: Date;
}

/** Ring status for one care type, or null when the plant table has no data for it. */
export function careStatus(plant: Plant, rp: RoomPlant, care: CareType, now: Date = new Date()): CareStatus | null {
  const interval = plant[CARE_FIELDS[care].interval] as number | null;
  if (!interval || interval <= 0) return null;
  const last = (rp[CARE_FIELDS[care].last] as string | null) ?? rp.created_at;
  const dueAt = new Date(new Date(last).getTime() + interval * DAY);
  const msLeft = dueAt.getTime() - now.getTime();
  const daysLeft = Math.ceil(msLeft / DAY);
  return {
    care,
    intervalDays: interval,
    daysLeft,
    fraction: Math.max(0, Math.min(1, msLeft / (interval * DAY))),
    overdue: msLeft <= 0,
    dueAt,
  };
}

export function allCareStatuses(plant: Plant, rp: RoomPlant, now: Date = new Date()): CareStatus[] {
  return (["water", "feed", "prune", "harvest"] as CareType[])
    .map((c) => careStatus(plant, rp, c, now))
    .filter((s): s is CareStatus => s !== null);
}

export function formatDaysLeft(daysLeft: number): string {
  if (daysLeft <= 0) return "now";
  return `${daysLeft}d`;
}
