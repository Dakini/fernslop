import { useRef, useState, type PointerEvent as RPE } from "react";
import grass from "@/assets/canvas-grass.jpg";
import emptyArt from "@/assets/empty-seedling.png";
import type { Plant, RoomArea, RoomPlant } from "@/services/types";
import { cn } from "@/lib/utils";
import { PlantAvatar } from "./PlantAvatar";
import { AREA_TONES } from "./CanvasThumbnail";

interface Props {
  plants: RoomPlant[];
  areas: RoomArea[];
  plantMap: Map<string, Plant>;
  freshId: string | null;
  onOpenPlant: (id: string) => void;
  onMovePlant: (id: string, x: number, y: number) => void;
  onUpdateArea: (id: string, patch: Partial<RoomArea>) => void;
  onSelectArea: (id: string | null) => void;
  selectedAreaId: string | null;
}

type Drag =
  | { kind: "plant"; id: string; moved: boolean }
  | { kind: "area-move"; id: string; dx: number; dy: number }
  | { kind: "area-resize"; id: string };

export function GardenCanvas(p: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [preview, setPreview] = useState<Record<string, { x: number; y: number; w?: number; h?: number }>>({});

  const pct = (e: RPE) => {
    const r = ref.current!.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * 100, y: ((e.clientY - r.top) / r.height) * 100 };
  };
  const clamp = (v: number) => Math.max(0, Math.min(100, v));

  function onMove(e: RPE) {
    if (!drag) return;
    const { x, y } = pct(e);
    if (drag.kind === "plant") {
      setDrag({ ...drag, moved: true });
      setPreview((s) => ({ ...s, [drag.id]: { x: clamp(x), y: clamp(y) } }));
    } else {
      const a = p.areas.find((a) => a.id === drag.id)!;
      if (drag.kind === "area-move")
        setPreview((s) => ({ ...s, [a.id]: { x: clamp(x - drag.dx), y: clamp(y - drag.dy), w: a.w_pct, h: a.h_pct } }));
      else
        setPreview((s) => ({ ...s, [a.id]: { x: a.x_pct, y: a.y_pct, w: Math.max(6, x - a.x_pct), h: Math.max(6, y - a.y_pct) } }));
    }
  }

  function onUp() {
    if (!drag) return;
    const pv = preview[drag.id];
    if (drag.kind === "plant") {
      if (drag.moved && pv) p.onMovePlant(drag.id, Math.round(pv.x), Math.round(pv.y));
      else p.onOpenPlant(drag.id);
    } else if (pv) {
      p.onUpdateArea(drag.id, { x_pct: Math.round(pv.x), y_pct: Math.round(pv.y), w_pct: Math.round(pv.w!), h_pct: Math.round(pv.h!) });
    }
    setDrag(null);
    setTimeout(() => setPreview({}), 400);
  }

  return (
    <div
      ref={ref}
      className="relative aspect-[4/3] w-full touch-none select-none overflow-hidden rounded-3xl border-4 border-oat bg-cover bg-center shadow-soft md:aspect-[3/2]"
      style={{ backgroundImage: `url(${grass})` }}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerLeave={onUp}
      onPointerDown={(e) => e.target === ref.current && p.onSelectArea(null)}
      aria-label="Garden canvas"
    >
      {p.areas.map((a) => {
        const pv = preview[a.id];
        const sel = p.selectedAreaId === a.id;
        return (
          <div
            key={a.id}
            className={cn(
              "absolute flex cursor-move items-start justify-center border-2 border-dashed p-1",
              AREA_TONES[a.colour] ?? AREA_TONES["soil"],
              a.shape === "ellipse" ? "rounded-full items-center" : "rounded-2xl",
              sel && "ring-4 ring-cream",
            )}
            style={{ left: `${pv?.x ?? a.x_pct}%`, top: `${pv?.y ?? a.y_pct}%`, width: `${pv?.w ?? a.w_pct}%`, height: `${pv?.h ?? a.h_pct}%` }}
            onPointerDown={(e) => {
              e.stopPropagation();
              p.onSelectArea(a.id);
              const { x, y } = pct(e);
              setDrag({ kind: "area-move", id: a.id, dx: x - a.x_pct, dy: y - a.y_pct });
            }}
          >
            <span className="rounded-full bg-cream/90 px-2 py-0.5 text-xs font-bold font-display text-moss">{a.label}</span>
            {sel && (
              <span
                aria-label="Resize area"
                className="absolute right-0 bottom-0 h-5 w-5 cursor-se-resize rounded-full border-2 border-moss bg-cream"
                onPointerDown={(e) => {
                  e.stopPropagation();
                  setDrag({ kind: "area-resize", id: a.id });
                }}
              />
            )}
          </div>
        );
      })}

      {p.plants.map((rp) => {
        const plant = p.plantMap.get(rp.plant_id);
        if (!plant) return null;
        const pv = preview[rp.id];
        const name = rp.nickname ?? plant.common_name;
        return (
          <button
            key={rp.id}
            type="button"
            aria-label={`${name}. Press Enter to open, arrow keys to move.`}
            className={cn(
              "absolute flex -translate-x-1/2 -translate-y-1/2 cursor-grab flex-col items-center gap-0.5 rounded-full focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cream",
              p.freshId === rp.id && "animate-bob",
              drag?.kind === "plant" && drag.id === rp.id && "z-10 cursor-grabbing",
            )}
            style={{ left: `${pv?.x ?? rp.x_pct}%`, top: `${pv?.y ?? rp.y_pct}%` }}
            onPointerDown={(e) => {
              e.stopPropagation();
              setDrag({ kind: "plant", id: rp.id, moved: false });
            }}
            onKeyDown={(e) => {
              const d = e.shiftKey ? 10 : 2;
              const map: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] };
              if (map[e.key]) {
                e.preventDefault();
                p.onMovePlant(rp.id, rp.x_pct + map[e.key]![0], rp.y_pct + map[e.key]![1]);
              } else if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                p.onOpenPlant(rp.id);
              }
            }}
          >
            <PlantAvatar plant={plant} className="h-12 w-12 border-4 border-cream shadow-token md:h-14 md:w-14" />
            <span className="max-w-24 truncate rounded-full bg-cream px-2 text-[11px] font-bold font-display text-moss shadow-token">{name}</span>
          </button>
        );
      })}

      {p.plants.length === 0 && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div className="flex flex-col items-center rounded-3xl bg-cream/90 p-5 text-center shadow-soft">
            <img src={emptyArt} alt="" width={1024} height={1024} className="h-24 w-24" />
            <p className="font-display font-extrabold text-moss">Add the first plant</p>
            <p className="text-sm text-muted-foreground">Tap the + button to get growing.</p>
          </div>
        </div>
      )}
    </div>
  );
}
