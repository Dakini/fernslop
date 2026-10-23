/**
 * The token from an emailed link. Links put it in the fragment (`#token=…`), which the browser
 * never sends, so it stays out of server and proxy logs; older unsubscribe links used
 * `?token=…`, which still works. (The `-` prefix keeps this file out of the route tree.)
 */
export function tokenFromUrl(hash: string, search: string): string | undefined {
  const fromHash = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  const fromSearch = new URLSearchParams(search).get("token");
  return fromHash || fromSearch || undefined;
}

/** The token of the current page's URL. Only call in the browser (the routes are `ssr: false`). */
export function currentToken(): string | undefined {
  return tokenFromUrl(window.location.hash, window.location.search);
}
