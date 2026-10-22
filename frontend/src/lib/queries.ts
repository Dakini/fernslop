import { queryOptions, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getServices } from "@/services";

export const roomsQuery = () =>
  queryOptions({ queryKey: ["rooms"], queryFn: () => getServices().listRooms() });

export const roomQuery = (roomId: string) =>
  queryOptions({ queryKey: ["room", roomId], queryFn: () => getServices().getRoomState(roomId) });

export const plantsQuery = () =>
  queryOptions({ queryKey: ["plants"], queryFn: () => getServices().listPlants(), staleTime: Infinity });

/** Live updates: refetch the room whenever the service reports a change. Returns connection status. */
export function useRoomLive(roomId: string) {
  const qc = useQueryClient();
  const [online, setOnline] = useState(true);
  useEffect(() => {
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
  }, [roomId, qc]);
  return online;
}
