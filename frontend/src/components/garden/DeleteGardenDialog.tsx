import { useState } from "react";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { RateLimitError } from "@/services/http/httpService";
import { getServices } from "@/services";

/**
 * "Delete garden" button + confirm dialog. The dialog is the only guard (no accounts).
 * `onPendingChange(true)` fires before the request so the page can ignore the live
 * "room is gone" update; it stays true after success because the caller navigates away.
 * A 404 (someone else deleted it first) counts as success.
 */
export function DeleteGardenDialog({
  roomId,
  roomName,
  onDeleted,
  onPendingChange,
}: {
  roomId: string;
  roomName: string;
  onDeleted: () => void;
  onPendingChange?: (pending: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);

  async function confirm() {
    if (pending) return;
    setPending(true);
    onPendingChange?.(true);
    try {
      await getServices().deleteRoom(roomId);
    } catch (e) {
      if (!(e instanceof RateLimitError)) toast.error((e as Error).message);
      setPending(false);
      onPendingChange?.(false);
      return;
    }
    onDeleted();
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(o) => {
        if (!pending) setOpen(o);
      }}
    >
      <AlertDialogTrigger asChild>
        <Button variant="outline" className="h-11 sm:h-9">
          <Trash2 /> Delete garden
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent
        className="w-[calc(100%-2rem)] rounded-3xl bg-cream"
        // Radix ignores outside clicks in an alert dialog; here they dismiss it like Cancel
        // (blocked while the request is in flight, like Cancel and Esc).
        overlayProps={{ onClick: () => !pending && setOpen(false) }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle className="font-display text-2xl font-extrabold text-moss">
            Delete “{roomName}”?
          </AlertDialogTitle>
          <AlertDialogDescription>
            Its plants, activity, photos and follower emails will be gone for
            good. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="gap-2 sm:gap-0">
          <AlertDialogCancel disabled={pending} className="mt-0 h-11 sm:h-9">
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            disabled={pending}
            className="h-11 bg-terracotta text-primary-foreground hover:bg-terracotta hover:brightness-105 sm:h-9"
            onClick={(e) => {
              e.preventDefault();
              void confirm();
            }}
          >
            Delete garden
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
