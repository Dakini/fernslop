import { infiniteQueryOptions, queryOptions, useInfiniteQuery, useQueryClient, useSuspenseQuery, type QueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { getServices, type FeedEvent, type FeedPage, type RoomState } from "@/services";

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

const NO_OLDER: FeedPage = { events: [], next: null };

/**
 * Feed pages older than the room state's newest events (#210), loaded only on demand. The first
 * page always starts at the state's *current* `feed_next`, so a refetch after the state changed
 * reloads every loaded page from there: nothing is skipped or shown twice.
 */
export const olderFeedQuery = (roomId: string, qc: QueryClient) =>
  infiniteQueryOptions({
    queryKey: ["roomFeed", roomId],
    queryFn: ({ pageParam }) => {
      const before = pageParam ?? qc.getQueryData<RoomState | null>(["room", roomId])?.feed_next ?? null;
      return before ? getServices().getRoomFeed(roomId, { before }) : Promise.resolve(NO_OLDER);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next,
    enabled: false,
  });

/**
 * The feed to show: the state's newest events plus any older pages loaded with `loadOlder`.
 * Whenever the state is refetched (live update, own write, undo) the loaded older pages are
 * refetched too, so they stay loaded and show undos; events are listed once, by id.
 */
export function useRoomFeed(roomId: string) {
  const qc = useQueryClient();
  const { data: state, dataUpdatedAt: stateUpdatedAt } = useSuspenseQuery(roomQuery(roomId));
  const older = useInfiniteQuery(olderFeedQuery(roomId, qc));
  const loaded = !!older.data?.pages.length;
  const { refetch } = older;

  useEffect(() => {
    if (loaded) void refetch();
    // Only when the room state changes; `loaded` is read, not watched.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateUpdatedAt, refetch]);

  const newest = state?.feed;
  const events = useMemo(() => {
    const seen = new Set<string>();
    const all: FeedEvent[] = [];
    for (const ev of [...(newest ?? []), ...(older.data?.pages.flatMap((p) => p.events) ?? [])]) {
      if (!seen.has(ev.id)) {
        seen.add(ev.id);
        all.push(ev);
      }
    }
    return all;
  }, [newest, older.data]);

  const hasOlder = loaded ? older.hasNextPage : !!state?.feed_next;
  const loadOlder = () => (loaded ? older.fetchNextPage() : older.refetch());
  const loadingOlder = older.isFetchingNextPage || (older.isFetching && !loaded);
  return { events, hasOlder, loadOlder, loadingOlder };
}

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
