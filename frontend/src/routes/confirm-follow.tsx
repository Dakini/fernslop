import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Sprout } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getServices } from "@/services";
import { currentToken } from "./-token";

export const Route = createFileRoute("/confirm-follow")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Confirm follow · Fernslop" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ConfirmFollowPage,
});

type Result = "pending" | "confirmed" | "invalid" | "failed";

const COPY: Record<
  Exclude<Result, "pending">,
  { title: string; body: string }
> = {
  confirmed: {
    title: "You're following this garden",
    body: "We'll send you a weekly digest when it's busy. Every email has a link to stop them.",
  },
  invalid: {
    title: "This link has expired or doesn't work",
    body: "Confirmation links last 7 days. Follow the garden again to get a new one.",
  },
  failed: {
    title: "We couldn't reach the garden",
    body: "Please check your connection and try the link again in a moment.",
  },
};

/** Confirms once with the token from the link; the email address is never shown. */
export function ConfirmFollowResult({ token }: { token?: string | undefined }) {
  const [result, setResult] = useState<Result>(token ? "pending" : "invalid");
  // Guards against React strict mode re-running the effect and posting twice.
  const request = useRef<Promise<boolean> | null>(null);

  useEffect(() => {
    if (!token) return;
    let live = true;
    request.current ??= getServices().confirmFollow(token);
    request.current.then(
      (done) => live && setResult(done ? "confirmed" : "invalid"),
      () => live && setResult("failed"),
    );
    return () => {
      live = false;
    };
  }, [token]);

  const copy = result === "pending" ? null : COPY[result];
  return (
    <main className="mx-auto max-w-md px-4 py-14 text-center">
      <p className="flex items-center justify-center gap-2 font-display font-bold text-sage">
        <Sprout className="h-5 w-5" /> Fernslop
      </p>
      <div
        className="mt-6 rounded-3xl bg-oat p-8 shadow-soft"
        role="status"
        aria-live="polite"
      >
        <h1 className="text-2xl">{copy ? copy.title : "Confirming…"}</h1>
        {copy && <p className="mt-2 text-muted-foreground">{copy.body}</p>}
      </div>
      {copy && (
        <Button asChild className="mt-6" variant="outline">
          <Link to="/">Visit the gardens</Link>
        </Button>
      )}
    </main>
  );
}

function ConfirmFollowPage() {
  const [token] = useState(currentToken);
  return <ConfirmFollowResult token={token} />;
}
