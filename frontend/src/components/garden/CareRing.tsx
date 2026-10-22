import { Droplets, Scissors, ShoppingBasket, Sprout } from "lucide-react";
import { formatDaysLeft, type CareStatus } from "@/services/care";
import type { CareType } from "@/services/types";
import { cn } from "@/lib/utils";

export const CARE_ICONS: Record<CareType, typeof Droplets> = {
  water: Droplets,
  feed: Sprout,
  prune: Scissors,
  harvest: ShoppingBasket,
};

export function CareRing({ status, size = 44 }: { status: CareStatus; size?: number }) {
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  const Icon = CARE_ICONS[status.care];
  return (
    <div
      className="relative flex flex-col items-center rounded-2xl bg-cream px-1.5 pt-1.5 pb-1"
      aria-label={`${status.care}: ${status.overdue ? "due now" : `${status.daysLeft} days left`}`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={4} className="stroke-oat" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - (status.overdue ? 1 : status.fraction))}
          className={cn("transition-all", status.overdue ? "stroke-terracotta" : "stroke-sage")}
        />
      </svg>
      <Icon className={cn("absolute top-[calc(0.375rem+50%-1.1rem)] h-4 w-4", status.overdue ? "text-terracotta" : "text-moss")} style={{ top: 6 + size / 2 - 8 }} />
      <span className={cn("text-[11px] font-bold font-display", status.overdue ? "text-terracotta" : "text-moss")}>
        {formatDaysLeft(status.daysLeft)}
      </span>
      {status.overdue && <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-terracotta" />}
    </div>
  );
}
