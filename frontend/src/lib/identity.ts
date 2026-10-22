import { useEffect, useState } from "react";
import type { Actor } from "@/services/types";

const ANIMALS = [
  "Hedgehog",
  "Toad",
  "Robin",
  "Badger",
  "Wren",
  "Newt",
  "Mole",
  "Bumblebee",
  "Ladybird",
  "Dormouse",
];
const KEY = "fernslop:identity";

/** Mirrors `backend/app/auth.py`. Lengths are code points, like Python `len`. */
export const NAME_MAX_LENGTH = 40;
export const DEVICE_ID_MAX_LENGTH = 64;

/**
 * Mirrors `backend/app/text.py`: control, format and line/paragraph separator characters are
 * rejected, except the zero-width joiner that holds emoji such as 👩‍🌾 together. Lone surrogates
 * (`Cs`) are rejected too: Python never sees them, and `encodeURIComponent` throws on them.
 */
const INVALID_CHARACTER = /(?!\u200d)[\p{Cc}\p{Cf}\p{Zl}\p{Zp}\p{Cs}]/u;

const codePoints = (s: string) => Array.from(s).length;

/** Why the backend would reject this nickname, or `null` if it is fine. Expects a trimmed, non-empty name. */
export function nicknameError(name: string): string | null {
  if (INVALID_CHARACTER.test(name))
    return "Your nickname contains invalid characters.";
  if (codePoints(name) > NAME_MAX_LENGTH)
    return `Your nickname must be at most ${NAME_MAX_LENGTH} characters.`;
  return null;
}

/** The trimmed name if the backend would accept it, else `null`. */
function cleanName(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const name = v.trim();
  return name !== "" && nicknameError(name) === null ? name : null;
}

/** The trimmed device id if the backend would accept it, else `null`. */
function cleanDeviceId(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const id = v.trim();
  return id !== "" && codePoints(id) <= DEVICE_ID_MAX_LENGTH ? id : null;
}

export function randomName(r: () => number = Math.random) {
  return `Anonymous ${ANIMALS[Math.floor(r() * ANIMALS.length)]}`;
}

/** `crypto.randomUUID` only exists in secure contexts (https/localhost); `getRandomValues` works over plain http on a LAN IP too. */
function newDeviceId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

/** The identity for this session, used when localStorage is unavailable (e.g. private mode). */
let memory: Actor | null = null;
let storageUsable = true;

function readStored(): unknown {
  const raw = localStorage.getItem(KEY);
  if (raw === null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function store(actor: Actor) {
  memory = actor;
  if (!storageUsable) return;
  try {
    localStorage.setItem(KEY, JSON.stringify(actor));
  } catch {
    storageUsable = false;
  }
}

/** The stored identity, repaired if broken: a valid half is kept and the other half generated. */
export function loadIdentity(): Actor {
  let stored: unknown;
  if (storageUsable) {
    try {
      stored = readStored();
    } catch {
      storageUsable = false;
    }
  }
  if (!storageUsable) {
    if (!memory) memory = { device_id: newDeviceId(), name: randomName() };
    return memory;
  }
  const obj =
    stored && typeof stored === "object" && !Array.isArray(stored)
      ? (stored as { device_id?: unknown; name?: unknown })
      : {};
  const device_id = cleanDeviceId(obj.device_id);
  const name = cleanName(obj.name);
  if (
    device_id !== null &&
    name !== null &&
    device_id === obj.device_id &&
    name === obj.name
  ) {
    memory = { device_id, name };
    return memory;
  }
  const repaired: Actor = {
    device_id: device_id ?? newDeviceId(),
    name: name ?? randomName(),
  };
  store(repaired);
  return repaired;
}

/** Saves a trimmed nickname. An empty one keeps the current name; an invalid one is not saved (check `nicknameError` first). */
export function saveNickname(name: string): Actor {
  const cur = loadIdentity();
  const trimmed = name.trim();
  if (!trimmed || nicknameError(trimmed)) return cur;
  const next = { ...cur, name: trimmed };
  store(next);
  window.dispatchEvent(new Event("fernslop:identity"));
  return next;
}

export function useIdentity(): Actor {
  const [actor, setActor] = useState<Actor>({
    name: "Anonymous Gardener",
    device_id: "pending",
  });
  useEffect(() => {
    setActor(loadIdentity());
    const on = () => setActor(loadIdentity());
    window.addEventListener("fernslop:identity", on);
    return () => window.removeEventListener("fernslop:identity", on);
  }, []);
  return actor;
}
