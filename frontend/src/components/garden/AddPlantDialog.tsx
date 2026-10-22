import { useEffect, useState } from "react";
import { Camera, Loader2, Search } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getServices, type IdentifyCandidate, type Plant } from "@/services";
import { PlantAvatar } from "./PlantAvatar";

const LOW_CONFIDENCE = 0.3;

export function AddPlantDialog({ open, onOpenChange, onPick }: { open: boolean; onOpenChange: (o: boolean) => void; onPick: (plant: Plant) => void }) {
  const [tab, setTab] = useState("search");
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Plant[]>([]);
  const [busy, setBusy] = useState(false);
  const [candidates, setCandidates] = useState<IdentifyCandidate[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    getServices().searchPlants(q).then((r) => live && setResults(r));
    return () => {
      live = false;
    };
  }, [q, open]);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setCandidates(null);
    setNotice(null);
    try {
      const c = await getServices().identifyPlant(file);
      if (!c.length || c[0]!.confidence < LOW_CONFIDENCE) {
        setNotice("We couldn't be sure — try searching instead");
        setTab("search");
      } else setCandidates(c);
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const row = (plant: Plant, extra?: string) => (
    <li key={plant.id}>
      <button type="button" onClick={() => onPick(plant)} className="flex w-full items-center gap-3 rounded-2xl bg-cream p-2 text-left hover:bg-clay/40">
        <PlantAvatar plant={plant} className="h-11 w-11" />
        <span className="flex-1">
          <span className="block font-display font-bold text-moss">{plant.common_name}</span>
          <span className="block text-xs italic text-muted-foreground">{plant.scientific_name}</span>
        </span>
        {extra && <span className="rounded-full bg-sage px-2 py-0.5 text-xs font-bold">{extra}</span>}
      </button>
    </li>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-3xl bg-oat sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-moss">Add a plant</DialogTitle>
          <DialogDescription>Search our plant table or snap a photo.</DialogDescription>
        </DialogHeader>
        {notice && <p role="status" className="rounded-2xl bg-clay/50 px-3 py-2 text-sm text-accent-foreground">{notice}</p>}
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid w-full grid-cols-2 rounded-full">
            <TabsTrigger value="search" className="rounded-full"><Search className="h-4 w-4" /> Search</TabsTrigger>
            <TabsTrigger value="photo" className="rounded-full"><Camera className="h-4 w-4" /> Photo</TabsTrigger>
          </TabsList>
          <TabsContent value="search" className="space-y-3">
            <Label htmlFor="plant-q" className="sr-only">Plant name</Label>
            <Input id="plant-q" autoFocus placeholder="Basil, Rosa, tomato…" value={q} onChange={(e) => setQ(e.target.value)} className="rounded-full bg-cream" />
            <ul className="max-h-80 space-y-2 overflow-y-auto">
              {results.map((p) => row(p))}
              {!results.length && <li className="py-6 text-center text-sm text-muted-foreground">No plants match “{q}”.</li>}
            </ul>
          </TabsContent>
          <TabsContent value="photo" className="space-y-3">
            <Label htmlFor="plant-photo" className="flex cursor-pointer flex-col items-center gap-2 rounded-3xl border-2 border-dashed border-sage bg-cream p-6 text-center">
              {busy ? <Loader2 className="h-8 w-8 animate-spin text-moss" /> : <Camera className="h-8 w-8 text-moss" />}
              <span className="font-display font-bold text-moss">{busy ? "Looking closely…" : "Upload a photo"}</span>
              <span className="text-xs text-muted-foreground">JPG, PNG or WebP up to 5 MB</span>
            </Label>
            <input id="plant-photo" type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = ""; }} />
            {candidates && (
              <>
                <p className="text-sm font-bold text-moss">Which one is it?</p>
                <ul className="space-y-2">{candidates.map((c) => row(c.plant, `${Math.round(c.confidence * 100)}%`))}</ul>
                <button type="button" className="text-sm underline" onClick={() => setTab("search")}>None of these — search instead</button>
              </>
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
