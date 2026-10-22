import { createFileRoute, Link } from "@tanstack/react-router";
import { useSuspenseInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, Search, Sprout } from "lucide-react";
import emptyArt from "@/assets/empty-seedling.png";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CanvasThumbnail } from "@/components/garden/CanvasThumbnail";
import { CreateRoomDialog } from "@/components/garden/CreateRoomDialog";
import { roomsQuery } from "@/lib/queries";
import type { RoomPage, RoomSummary } from "@/services/types";

export const Route = createFileRoute("/")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Fernslop — community gardens anyone can tend" },
      { name: "description", content: "Create a shared garden plan, arrange plants on a canvas and keep care ticking along together. No accounts needed." },
      { property: "og:title", content: "Fernslop — community gardens anyone can tend" },
      { property: "og:description", content: "A shared, living garden plan that anyone can help tend." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  loader: ({ context }) => context.queryClient.ensureInfiniteQueryData(roomsQuery()),
  component: Index,
});

/** All loaded pages in order; a room that moved to an earlier page between fetches is shown once. */
function loadedRooms(pages: RoomPage[]): RoomSummary[] {
  const seen = new Set<string>();
  return pages.flatMap((p) => p.rooms).filter((s) => !seen.has(s.room.id) && seen.add(s.room.id));
}

function Index() {
  const { data, hasNextPage, fetchNextPage, isFetchingNextPage } = useSuspenseInfiniteQuery(roomsQuery());
  const [q, setQ] = useState("");
  const all = loadedRooms(data.pages);
  const rooms = all.filter((r) => r.room.name.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 md:py-14">
      <header className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="flex items-center gap-2 font-display font-bold text-sage"><Sprout className="h-5 w-5" /> Fernslop</p>
          <h1 className="mt-1 text-4xl md:text-5xl">Gardens anyone can tend</h1>
          <p className="mt-2 max-w-lg text-muted-foreground">Shared garden plans for allotments, back gardens and balconies. No accounts — just open a garden and lend a hand.</p>
        </div>
        <CreateRoomDialog>
          <Button size="lg"><Plus /> Create a room</Button>
        </CreateRoomDialog>
      </header>

      <div className="relative mt-8 max-w-sm">
        <Search className="absolute top-1/2 left-4 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <label htmlFor="room-search" className="sr-only">Search gardens</label>
        <Input id="room-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search gardens" className="rounded-full bg-oat pl-10" />
      </div>

      {all.length === 0 ? (
        <div className="mt-12 flex flex-col items-center text-center">
          <img src={emptyArt} alt="" width={1024} height={1024} className="h-40 w-40" />
          <h2 className="text-2xl">No gardens yet</h2>
          <CreateRoomDialog><Button className="mt-4" size="lg">Plant the first garden</Button></CreateRoomDialog>
        </div>
      ) : (
        <ul className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {rooms.map((s) => (
            <li key={s.room.id}>
              <Link to="/r/$roomId" params={{ roomId: s.room.id }} className="block rounded-3xl bg-oat p-3 shadow-soft transition-transform hover:-translate-y-1 focus-visible:ring-4 focus-visible:ring-sage focus-visible:outline-none">
                <CanvasThumbnail summary={s} />
                <div className="px-2 pt-3 pb-1">
                  <h2 className="text-lg">{s.room.name}</h2>
                  <p className="text-sm text-muted-foreground">{s.plants.length} plants{s.room.region && ` · ${s.room.region}`}</p>
                </div>
              </Link>
            </li>
          ))}
          {!rooms.length && <li className="text-muted-foreground">No gardens match “{q}”.</li>}
        </ul>
      )}

      {hasNextPage && (
        <div className="mt-8 flex justify-center">
          <Button variant="soft" size="lg" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
            {isFetchingNextPage ? "Loading gardens…" : "Show more gardens"}
          </Button>
        </div>
      )}
    </main>
  );
}
