import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Sprout } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getServices } from "@/services";

export const Route = createFileRoute("/unsubscribe")({
  ssr: false,
  validateSearch: (search: Record<string, unknown>): { token?: string } => ({
    token:
      typeof search.token === "string" && search.token
        ? search.token
        : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Unsubscribe · Fernslop" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: UnsubscribePage,
});

type Result = "pending" | "unsubscribed" | "already" | "missing" | "failed";

const COPY: Record<
  Exclude<Result, "pending">,
  { title: string; body: string }
> = {
  unsubscribed: {
    title: "You're unsubscribed",
    body: "We won't send you any more digests for this garden.",
  },
  already: {
    title: "Already unsubscribed",
    body: "This link has been used already, so there's nothing more to do.",
  },
  missing: {
    title: "This link looks incomplete",
    body: "Try opening the unsubscribe link from your email again.",
  },
  failed: {
    title: "We couldn't reach the garden",
    body: "Please check your connection and try the link again in a moment.",
  },
};

/** The token is read from the URL and sent in the request body only. */
export function UnsubscribeResult({ token }: { token?: string }) {
  const [result, setResult] = useState<Result>(token ? "pending" : "missing");
  // Guards against React strict mode re-running the effect and posting twice.
  const request = useRef<Promise<boolean> | null>(null);

  useEffect(() => {
    if (!token) return;
    let live = true;
    request.current ??= getServices().unfollow(token);
    request.current.then(
      (done) => live && setResult(done ? "unsubscribed" : "already"),
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
        <h1 className="text-2xl">{copy ? copy.title : "Unsubscribing…"}</h1>
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

function UnsubscribePage() {
  const { token } = Route.useSearch();
  return <UnsubscribeResult token={token} />;
}
