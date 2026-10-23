import { useState, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { getServices } from "@/services";
import { RateLimitError } from "@/services/http/httpService";

export function shareUrl(roomId: string) {
  return `${window.location.origin}/r/${roomId}`;
}
/** `navigator.clipboard` is missing on plain-http origins (e.g. a LAN IP), so fall back to a hidden textarea. */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to the legacy path */
  }
  const el = document.createElement("textarea");
  el.value = text;
  el.style.position = "fixed";
  el.style.opacity = "0";
  document.body.appendChild(el);
  el.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    el.remove();
  }
}

export async function copyShare(roomId: string) {
  const url = shareUrl(roomId);
  if (await copyText(url)) toast.success("Link copied — send it to your fellow gardeners");
  else toast.error(`Couldn't copy automatically — the link is ${url}`, { duration: 15000 });
}

export function CreateRoomDialog({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();
  const qc = useQueryClient();

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const room = await getServices().createRoom({
        name: String(f.get("name") ?? ""),
        description: String(f.get("description") ?? ""),
        region: String(f.get("region") ?? ""),
      });
      qc.invalidateQueries({ queryKey: ["rooms"] });
      setOpen(false);
      await nav({ to: "/r/$roomId", params: { roomId: room.id } });
      toast("Share this garden", { action: { label: "Copy link", onClick: () => copyShare(room.id) }, duration: 10000 });
    } catch (err) {
      if (!(err instanceof RateLimitError)) setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="rounded-3xl bg-oat sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-moss">Plant a new garden</DialogTitle>
          <DialogDescription>Anyone with the link can help tend it.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="room-name">Garden name</Label>
            <Input id="room-name" name="name" required maxLength={60} placeholder="Gran's allotment" className="rounded-full bg-cream" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="room-desc">Short description (optional)</Label>
            <Textarea id="room-desc" name="description" maxLength={200} className="rounded-2xl bg-cream" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="room-region">Country / region (optional)</Label>
            <Input id="room-region" name="region" maxLength={60} placeholder="Cardiff, UK" className="rounded-full bg-cream" />
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy ? "Planting…" : "Create garden"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
