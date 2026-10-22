import { useEffect, useState } from "react";
import type { Actor } from "@/services/types";

const ANIMALS = ["Hedgehog", "Toad", "Robin", "Badger", "Wren", "Newt", "Mole", "Bumblebee", "Ladybird", "Dormouse"];
const KEY = "fernslop:identity";

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

export function loadIdentity(): Actor {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw) as Actor;
  } catch {
    /* ignore */
  }
  const id: Actor = { device_id: newDeviceId(), name: randomName() };
  try {
    localStorage.setItem(KEY, JSON.stringify(id));
  } catch {
    /* ignore */
  }
  return id;
}

export function saveNickname(name: string): Actor {
  const cur = loadIdentity();
  const next = { ...cur, name: name.trim().slice(0, 40) || cur.name };
  localStorage.setItem(KEY, JSON.stringify(next));
  window.dispatchEvent(new Event("fernslop:identity"));
  return next;
}

export function useIdentity(): Actor {
  const [actor, setActor] = useState<Actor>({ name: "Anonymous Gardener", device_id: "pending" });
  useEffect(() => {
    setActor(loadIdentity());
    const on = () => setActor(loadIdentity());
    window.addEventListener("fernslop:identity", on);
    return () => window.removeEventListener("fernslop:identity", on);
  }, []);
  return actor;
}
