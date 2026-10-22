import { createFileRoute, Link, notFound, useNavigate } from "@tanstack/react-router";
import { useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, Bell, Check, ImagePlus, Pencil, Plus, Share2, Square, Circle, Trash2, Undo2, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { GardenCanvas } from "@/components/garden/GardenCanvas";
import { AddPlantDialog } from "@/components/garden/AddPlantDialog";
import { PlantAvatar } from "@/components/garden/PlantAvatar";
import { CareRing, CARE_ICONS } from "@/components/garden/CareRing";
import { copyShare } from "@/components/garden/CreateRoomDialog";
import { DeleteGardenDialog } from "@/components/garden/DeleteGardenDialog";
import { plantsQuery, roomQuery, useRoomLive } from "@/lib/queries";
import { nicknameError, saveNickname, useIdentity } from "@/lib/identity";
import { allCareStatuses, CARE_LABELS, type CareStatus } from "@/services/care";
import { getServices, CARE_TYPES, type CareType, type Photo, type Plant, type PlantCategory, type RoomPlant } from "@/services";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/r/$roomId")({
  ssr: false,
  loader: async ({ context, params }) => {
    const [state] = await Promise.all([
      context.queryClient.ensureQueryData(roomQuery(params.roomId)),
      context.queryClient.ensureQueryData(plantsQuery()),
    ]);
    if (!state) throw notFound();
    return { name: state.room.name, description: state.room.description };
  },
  head: ({ loaderData }) => ({
    meta: [
      { title: loaderData ? `${loaderData.name} · Fernslop` : "Garden · Fernslop" },
      { name: "description", content: loaderData?.description || "A shared garden anyone can help tend." },
      { property: "og:title", content: loaderData ? `${loaderData.name} · Fernslop` : "Garden · Fernslop" },
      { property: "og:description", content: loaderData?.description || "A shared garden anyone can help tend." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  notFoundComponent: () => (
    <div className="p-10 text-center">
      <h1 className="text-2xl">This garden can't be found</h1>
      <Link to="/" className="mt-4 inline-block underline">Back to all gardens</Link>
    </div>
  ),
  component: RoomPage,
});

const FILTERS: { label: string; value: PlantCategory | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Flowers", value: "flower" },
  { label: "Vegetables", value: "vegetable" },
  { label: "Herbs", value: "herb" },
  { label: "Houseplants", value: "houseplant" },
];

function RoomPage() {
  const { roomId } = Route.useParams();
  const { data: state } = useSuspenseQuery(roomQuery(roomId));
  const { data: plants } = useSuspenseQuery(plantsQuery());
  const qc = useQueryClient();
  const actor = useIdentity();
  const navigate = useNavigate();
  // True from the moment this visitor confirms a delete, so the live "room is gone" update never shows them the deleted page.
  const [deleting, setDeleting] = useState(false);
  const online = useRoomLive(roomId, !!state);
  const svc = getServices();

  const [openPlantId, setOpenPlantId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [freshId, setFreshId] = useState<string | null>(null);
  const [areaId, setAreaId] = useState<string | null>(null);
  const plantMap = useMemo(() => new Map(plants.map((p) => [p.id, p])), [plants]);
  const now = new Date();

  if (!state) return deleting ? null : <GardenDeleted />;
  const { room } = state;

  async function afterDelete() {
    qc.removeQueries({ queryKey: ["rooms"] });
    await navigate({ to: "/" });
    qc.removeQueries({ queryKey: ["room", roomId] });
    toast.success("Garden deleted");
  }

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["room", roomId] });
      if (ok) toast.success(ok);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const tasks = state.plants
    .flatMap((rp) => {
      const plant = plantMap.get(rp.plant_id);
      return plant ? allCareStatuses(plant, rp, now).map((s) => ({ rp, plant, s })) : [];
    })
    .sort((a, b) => a.s.dueAt.getTime() - b.s.dueAt.getTime());
  const dueTasks = tasks.filter((t) => t.s.daysLeft <= 3);

  const openRp = state.plants.find((p) => p.id === openPlantId) ?? null;
  const selectedArea = state.areas.find((a) => a.id === areaId) ?? null;

  async function pick(plant: Plant) {
    setAdding(false);
    const rp = await svc.addPlant(room.id, plant.id, actor);
    setFreshId(rp.id);
    await qc.invalidateQueries({ queryKey: ["room", roomId] });
    toast.success(`${plant.common_name} planted — drag it into place`);
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-5 pb-28">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-moss"><ArrowLeft className="h-4 w-4" /> All gardens</Link>
          <h1 className="text-3xl md:text-4xl">{room.name}</h1>
          {(room.description || room.region) && (
            <p className="text-muted-foreground">{room.description}{room.region && <span className="ml-1 text-sm">· {room.region}</span>}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <NicknameChip name={actor.name} />
          <FollowButton roomId={room.id} />
          <Button variant="secondary" onClick={() => copyShare(room.id)}><Share2 /> Share</Button>
          <DeleteGardenDialog roomId={room.id} roomName={room.name} onPendingChange={setDeleting} onDeleted={() => void afterDelete()} />
        </div>
      </header>

      {!online && (
        <p role="status" className="mt-3 inline-flex items-center gap-2 rounded-full bg-clay px-3 py-1 text-sm font-bold"><WifiOff className="h-4 w-4" /> Reconnecting…</p>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_380px]">
        <section className="space-y-3">
          <GardenCanvas
            plants={state.plants}
            areas={state.areas}
            plantMap={plantMap}
            freshId={freshId}
            selectedAreaId={areaId}
            onSelectArea={setAreaId}
            onOpenPlant={setOpenPlantId}
            onMovePlant={(id, x, y) => run(() => svc.movePlant(id, x, y, actor))}
            onUpdateArea={(id, patch) => run(() => svc.updateArea(id, patch, actor))}
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-moss">Add area:</span>
            <Button size="sm" variant="soft" onClick={() => run(() => svc.addArea(room.id, { label: "Veg bed", shape: "rect", x_pct: 35, y_pct: 35, w_pct: 30, h_pct: 30, colour: "soil" }, actor))}><Square /> Bed</Button>
            <Button size="sm" variant="soft" onClick={() => run(() => svc.addArea(room.id, { label: "Pond", shape: "ellipse", x_pct: 40, y_pct: 40, w_pct: 22, h_pct: 22, colour: "water" }, actor))}><Circle /> Pond</Button>
            {selectedArea && <AreaEditor key={selectedArea.id} label={selectedArea.label} onRename={(label) => run(() => svc.updateArea(selectedArea.id, { label }, actor))} onDelete={() => { setAreaId(null); run(() => svc.deleteArea(selectedArea.id, actor)); }} />}
          </div>
        </section>

        <aside className="rounded-3xl bg-oat p-3 shadow-soft">
          <Tabs defaultValue="plants">
            <TabsList className="grid w-full grid-cols-3 rounded-full bg-cream">
              <TabsTrigger value="plants" className="rounded-full">Plants</TabsTrigger>
              <TabsTrigger value="tasks" className="rounded-full">Tasks{dueTasks.length > 0 && <span className="ml-1 rounded-full bg-terracotta px-1.5 text-xs text-primary-foreground">{dueTasks.length}</span>}</TabsTrigger>
              <TabsTrigger value="feed" className="rounded-full">Feed</TabsTrigger>
            </TabsList>
            <TabsContent value="plants"><PlantsList rps={state.plants} plantMap={plantMap} now={now} onOpen={setOpenPlantId} /></TabsContent>
            <TabsContent value="tasks">
              <ul className="space-y-2">
                {tasks.length === 0 && <li className="p-6 text-center text-sm text-muted-foreground">Nothing to do yet — add a plant.</li>}
                {tasks.map(({ rp, plant, s }) => {
                  const Icon = CARE_ICONS[s.care];
                  const name = rp.nickname ?? plant.common_name;
                  return (
                    <li key={rp.id + s.care} className={cn("flex items-center gap-3 rounded-2xl p-2.5", s.overdue ? "bg-clay/60" : "bg-cream")}>
                      <Icon className={cn("h-5 w-5", s.overdue ? "text-terracotta" : "text-moss")} />
                      <span className="flex-1 text-sm">
                        <span className="block font-bold">{s.overdue ? CARE_LABELS[s.care].overdue(name) : `${CARE_LABELS[s.care].verb.replace("Mark ", "")}: ${name}`}</span>
                        <span className="text-xs text-muted-foreground">{s.overdue ? "Due now" : `In ${s.daysLeft} day${s.daysLeft === 1 ? "" : "s"}`}</span>
                      </span>
                      <Button size="icon" variant="outline" aria-label={`${CARE_LABELS[s.care].verb}: ${name}`} onClick={() => run(() => svc.markCare(rp.id, s.care, actor))}><Check /></Button>
                    </li>
                  );
                })}
              </ul>
            </TabsContent>
            <TabsContent value="feed">
              <PostBox onPost={(text, photo) => run(() => svc.postUpdate(room.id, text, photo, actor))} />
              <ul className="mt-3 space-y-2">
                {state.feed.map((ev) => (
                  <li key={ev.id} className={cn("rounded-2xl bg-cream p-3 text-sm", ev.undone_at && "opacity-60")}>
                    <p>
                      <span className="font-bold text-moss">{ev.actor_name}</span>{" "}
                      {ev.type === "post" ? <span className="block whitespace-pre-wrap pt-1">{ev.text}</span> : <span className={cn(ev.undone_at && "line-through")}>{ev.text}</span>}
                    </p>
                    {ev.photo_url && <img src={ev.photo_url} alt={`Photo from ${ev.actor_name}`} loading="lazy" className="mt-2 max-h-60 rounded-xl object-cover" />}
                    <p className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                      {new Date(ev.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                      {ev.undo_payload && !ev.undone_at && (
                        <button type="button" className="inline-flex items-center gap-1 font-bold text-terracotta underline" onClick={() => run(() => svc.undoEvent(ev.id, actor), "Undone")}><Undo2 className="h-3 w-3" /> Undo</button>
                      )}
                      {ev.undone_at && <span>Undone</span>}
                    </p>
                  </li>
                ))}
              </ul>
            </TabsContent>
          </Tabs>
        </aside>
      </div>

      <Button variant="fab" size="fab" aria-label="Add plant" className="fixed right-5 bottom-5 z-20" onClick={() => setAdding(true)}><Plus /></Button>
      <AddPlantDialog open={adding} onOpenChange={setAdding} onPick={pick} />

      <Sheet open={!!openRp} onOpenChange={(o) => !o && setOpenPlantId(null)}>
        <SheetContent className="overflow-y-auto bg-oat">
          {openRp && plantMap.get(openRp.plant_id) && (
            <PlantDrawer
              rp={openRp}
              plant={plantMap.get(openRp.plant_id)!}
              now={now}
              onCare={(c) => run(() => svc.markCare(openRp.id, c, actor), `${CARE_LABELS[c].done.charAt(0).toUpperCase()}${CARE_LABELS[c].done.slice(1)}!`)}
              onRemove={() => { setOpenPlantId(null); run(() => svc.removePlant(openRp.id, actor), "Removed — you can undo it from the feed"); }}
            />
          )}
        </SheetContent>
      </Sheet>
    </main>
  );
}

/** Shown to a visitor whose open garden was deleted by someone else. */
export function GardenDeleted() {
  return (
    <div className="p-10 text-center">
      <h1 className="text-2xl">This garden was deleted</h1>
      <Link to="/" className="mt-4 inline-block underline">All gardens</Link>
    </div>
  );
}

function Rings({ statuses, small }: { statuses: CareStatus[]; small?: boolean }) {
  return <div className="flex gap-1.5">{statuses.map((s) => <CareRing key={s.care} status={s} size={small ? 34 : 48} />)}</div>;
}

function PlantsList({ rps, plantMap, now, onOpen }: { rps: RoomPlant[]; plantMap: Map<string, Plant>; now: Date; onOpen: (id: string) => void }) {
  const [filter, setFilter] = useState<PlantCategory | "all">("all");
  const list = rps.filter((rp) => filter === "all" || plantMap.get(rp.plant_id)?.category === filter);
  return (
    <>
      <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="Filter plants">
        {FILTERS.map((f) => (
          <button key={f.value} type="button" aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}
            className={cn("rounded-full px-3 py-1 text-xs font-bold font-display", filter === f.value ? "bg-moss text-primary-foreground" : "bg-cream text-moss")}>{f.label}</button>
        ))}
      </div>
      <ul className="space-y-2">
        {list.length === 0 && <li className="p-6 text-center text-sm text-muted-foreground">No plants here yet.</li>}
        {list.map((rp) => {
          const plant = plantMap.get(rp.plant_id);
          if (!plant) return null;
          const st = allCareStatuses(plant, rp, now);
          return (
            <li key={rp.id}>
              <button type="button" onClick={() => onOpen(rp.id)} className="flex w-full items-center gap-3 rounded-2xl bg-cream p-2.5 text-left hover:bg-clay/30">
                <PlantAvatar plant={plant} className="h-14 w-14 shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-display font-extrabold text-moss">{rp.nickname ?? plant.common_name}</span>
                  {st.length ? <Rings statuses={st} small /> : <span className="text-xs text-muted-foreground">No care data available</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function PlantDrawer({ rp, plant, now, onCare, onRemove }: { rp: RoomPlant; plant: Plant; now: Date; onCare: (c: CareType) => void; onRemove: () => void }) {
  const statuses = allCareStatuses(plant, rp, now);
  const missing = CARE_TYPES.filter((c) => !statuses.some((s) => s.care === c));
  return (
    <>
      <SheetHeader className="items-center text-center">
        <PlantAvatar plant={plant} className="h-24 w-24 border-4 border-cream" />
        <SheetTitle className="font-display text-2xl text-moss">{rp.nickname ?? plant.common_name}</SheetTitle>
        <SheetDescription className="italic">{plant.scientific_name}</SheetDescription>
      </SheetHeader>
      <div className="space-y-5 px-4 pb-6">
        <p className="text-sm">{plant.description}</p>
        {statuses.length > 0 && <Rings statuses={statuses} />}
        {missing.includes("water") && <p className="text-xs text-muted-foreground">No watering data available</p>}
        <div className="grid grid-cols-2 gap-2">
          {statuses.map((s) => {
            const Icon = CARE_ICONS[s.care];
            return <Button key={s.care} variant={s.overdue ? "fab" : "secondary"} onClick={() => onCare(s.care)}><Icon /> {CARE_LABELS[s.care].verb}</Button>;
          })}
        </div>
        {statuses.find((s) => s.overdue) && <p className="text-sm text-terracotta">{CARE_LABELS[statuses.find((s) => s.overdue)?.care ?? "water"].overdue(plant.common_name)}</p>}
        <p className="text-xs text-muted-foreground">Added by {rp.added_by_name}. Care data: <a href={plant.source_url} target="_blank" rel="noreferrer" className="underline">{plant.source}</a></p>
        <Button variant="outline" className="w-full" onClick={onRemove}><Trash2 /> Remove plant</Button>
      </div>
    </>
  );
}

function AreaEditor({ label, onRename, onDelete }: { label: string; onRename: (l: string) => void; onDelete: () => void }) {
  const [v, setV] = useState(label);
  return (
    <form className="flex items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); if (v.trim() && v !== label) onRename(v.trim()); }}>
      <Label htmlFor="area-label" className="sr-only">Area name</Label>
      <Input id="area-label" value={v} onChange={(e) => setV(e.target.value)} className="h-8 w-32 rounded-full bg-cream" />
      <Button size="sm" type="submit" variant="secondary"><Pencil /> Rename</Button>
      <Button size="sm" type="button" variant="outline" onClick={onDelete} aria-label="Delete area"><Trash2 /></Button>
    </form>
  );
}

function PostBox({ onPost }: { onPost: (text: string, photoId: string | null) => Promise<unknown> }) {
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState<Photo | null>(null);
  const [uploading, setUploading] = useState(false);
  async function onFile(f?: File) {
    if (!f) return;
    setUploading(true);
    try {
      setPhoto(await getServices().uploadPhoto(f));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setUploading(false);
    }
  }
  return (
    <form className="space-y-2" onSubmit={async (e) => { e.preventDefault(); await onPost(text, photo?.id ?? null); setText(""); setPhoto(null); }}>
      <Label htmlFor="post-text" className="sr-only">Post an update</Label>
      <Textarea id="post-text" value={text} onChange={(e) => setText(e.target.value)} placeholder="Share an update with the garden…" className="rounded-2xl bg-cream" />
      {photo && <img src={photo.url} alt="Photo to post" className="max-h-32 rounded-xl" />}
      <div className="flex justify-between">
        <Label htmlFor="post-photo" className="inline-flex cursor-pointer items-center gap-1 text-sm font-bold text-moss"><ImagePlus className="h-4 w-4" /> {uploading ? "Uploading…" : "Photo"}</Label>
        <input id="post-photo" type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" disabled={uploading} onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = ""; }} />
        <Button size="sm" type="submit" disabled={uploading || (!text.trim() && !photo)}>Post</Button>
      </div>
    </form>
  );
}

function NicknameChip({ name }: { name: string }) {
  const [v, setV] = useState("");
  const [err, setErr] = useState<string | null>(null);
  return (
    <Popover onOpenChange={(o) => { if (o) { setV(name); setErr(null); } }}>
      <PopoverTrigger asChild>
        <button type="button" className="rounded-full bg-oat px-3 py-2 text-sm">You're <b className="text-moss">{name}</b> · <span className="underline">change</span></button>
      </PopoverTrigger>
      <PopoverContent className="rounded-2xl bg-cream">
        <form className="space-y-2" onSubmit={(e) => {
          e.preventDefault();
          const problem = v.trim() ? nicknameError(v.trim()) : null;
          setErr(problem);
          if (problem) return;
          saveNickname(v);
          toast.success("Nickname saved");
        }}>
          <Label htmlFor="nick">Your nickname</Label>
          <Input id="nick" value={v} onChange={(e) => { setV(e.target.value); setErr(null); }} aria-invalid={!!err} aria-describedby={err ? "nick-error" : undefined} className="rounded-full" />
          {err && <p id="nick-error" role="alert" className="text-xs text-destructive">{err}</p>}
          <Button type="submit" size="sm" className="w-full">Save</Button>
        </form>
      </PopoverContent>
    </Popover>
  );
}

function FollowButton({ roomId }: { roomId: string }) {
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  return (
    <Popover>
      <PopoverTrigger asChild><Button variant="soft"><Bell /> Follow</Button></PopoverTrigger>
      <PopoverContent className="rounded-2xl bg-cream">
        {done ? <p className="text-sm">You'll get a weekly digest when this garden is busy. 🌱</p> : (
          <form className="space-y-2" onSubmit={async (e) => {
            e.preventDefault();
            try { await getServices().followRoom(roomId, email); setDone(true); } catch (x) { setErr((x as Error).message); }
          }}>
            <Label htmlFor="follow-email">Email for weekly updates</Label>
            <Input id="follow-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="rounded-full" />
            {err && <p role="alert" className="text-xs text-destructive">{err}</p>}
            <Button type="submit" size="sm" className="w-full">Follow garden</Button>
          </form>
        )}
      </PopoverContent>
    </Popover>
  );
}
