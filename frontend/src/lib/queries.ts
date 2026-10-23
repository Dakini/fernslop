import { infiniteQueryOptions, queryOptions, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getServices } from "@/services";

/** The index, one page per `listRooms` call. A refetch reloads as many pages as were loaded. */
export const roomsQuery = () =>
  infiniteQueryOptions({
    queryKey: ["rooms"],
    queryFn: ({ pageParam }) => getServices().listRooms({ before: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next,
  });

export const roomQuery = (roomId: string) =>
  queryOptions({ queryKey: ["room", roomId], queryFn: () => getServices().getRoomState(roomId) });

export const plantsQuery = () =>
  queryOptions({ queryKey: ["plants"], queryFn: () => getServices().listPlants(), staleTime: Infinity });

/**
 * Live updates: refetch the room whenever the service reports a change. Returns connection status.
 * Pass `enabled = false` once the room is gone to close the subscription for good.
 */
export function useRoomLive(roomId: string, enabled = true) {
  const qc = useQueryClient();
  const [online, setOnline] = useState(true);
  useEffect(() => {
    if (!enabled) return;
    const off = getServices().subscribe(roomId, () => {
      qc.invalidateQueries({ queryKey: ["room", roomId] });
      qc.invalidateQueries({ queryKey: ["rooms"] });
    });
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    setOnline(navigator.onLine);
    return () => {
      off();
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, [roomId, qc, enabled]);
  return online;
}
