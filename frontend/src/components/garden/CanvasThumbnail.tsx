import grass from "@/assets/canvas-grass.jpg";
import type { RoomSummary } from "@/services/types";
import { cn } from "@/lib/utils";
import { categoryTone } from "./PlantAvatar";

export const AREA_TONES: Record<string, string> = {
  soil: "bg-soil/45 border-soil",
  water: "bg-pond/55 border-pond",
  sage: "bg-sage/45 border-moss/50",
  clay: "bg-clay/50 border-terracotta/60",
};

export function CanvasThumbnail({ summary }: { summary: RoomSummary }) {
  return (
    <div className="relative aspect-[3/2] overflow-hidden rounded-2xl bg-cover bg-center" style={{ backgroundImage: `url(${grass})` }}>
      {summary.areas.map((a) => (
        <div
          key={a.id}
          className={cn("absolute border-2 border-dashed", AREA_TONES[a.colour] ?? AREA_TONES["soil"], a.shape === "ellipse" ? "rounded-full" : "rounded-lg")}
          style={{ left: `${a.x_pct}%`, top: `${a.y_pct}%`, width: `${a.w_pct}%`, height: `${a.h_pct}%` }}
        />
      ))}
      {summary.plants.map((p, i) => (
        <span
          key={i}
          className={cn("absolute h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-cream", categoryTone(p.category))}
          style={{ left: `${p.x_pct}%`, top: `${p.y_pct}%` }}
        />
      ))}
    </div>
  );
}
