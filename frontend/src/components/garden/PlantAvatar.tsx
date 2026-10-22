import { Carrot, Flower2, Leaf, Shrub, Sprout, TreeDeciduous } from "lucide-react";
import type { Plant, PlantCategory } from "@/services/types";
import { cn } from "@/lib/utils";

const ICONS: Record<PlantCategory, typeof Leaf> = {
  flower: Flower2,
  vegetable: Carrot,
  herb: Sprout,
  houseplant: Leaf,
  shrub: Shrub,
  tree: TreeDeciduous,
};

const TONES: Record<PlantCategory, string> = {
  flower: "bg-clay text-accent-foreground",
  vegetable: "bg-terracotta text-primary-foreground",
  herb: "bg-sage text-secondary-foreground",
  houseplant: "bg-moss text-primary-foreground",
  shrub: "bg-sage text-primary-foreground",
  tree: "bg-soil text-primary-foreground",
};

export function categoryTone(c: PlantCategory) {
  return TONES[c];
}

export function PlantAvatar({ plant, className }: { plant: Pick<Plant, "category" | "image_url" | "common_name">; className?: string }) {
  const Icon = ICONS[plant.category];
  if (plant.image_url)
    return <img src={plant.image_url} alt={plant.common_name} className={cn("rounded-full object-cover", className)} />;
  return (
    <span role="img" aria-label={plant.common_name} className={cn("grid place-items-center rounded-full", TONES[plant.category], className)}>
      <Icon className="h-1/2 w-1/2" strokeWidth={1.8} />
    </span>
  );
}
