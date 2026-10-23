import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UnsubscribeResult } from "@/routes/unsubscribe";
import { tokenFromUrl } from "@/routes/-token";
import { setServices, type GardenService } from "@/services";

const useService = (unfollow: GardenService["unfollow"]) =>
  setServices({ unfollow } as GardenService);

afterEach(() => setServices(null));

// Link needs a router, so stub it out; the page logic is what's under test.
vi.mock("@tanstack/react-router", async (orig) => ({
  ...(await orig<typeof import("@tanstack/react-router")>()),
  Link: ({ children }: { children: React.ReactNode }) => (
    <a href="/">{children}</a>
  ),
}));

describe("unsubscribe page", () => {
  it("sends the token and shows the unsubscribed and already-unsubscribed results", async () => {
    const unfollow = vi.fn().mockResolvedValueOnce(true);
    useService(unfollow);
    const first = render(<UnsubscribeResult token="tok-1" />);
    expect(await screen.findByText("You're unsubscribed")).toBeInTheDocument();
    expect(unfollow).toHaveBeenCalledWith("tok-1");
    first.unmount();

    useService(vi.fn().mockResolvedValue(false));
    render(<UnsubscribeResult token="used" />);
    expect(await screen.findByText("Already unsubscribed")).toBeInTheDocument();
  });

  it("shows a friendly message for a missing token or network failure without erroring", async () => {
    const unfollow = vi.fn().mockRejectedValue(new Error("offline"));
    useService(unfollow);
    const none = render(<UnsubscribeResult />);
    expect(screen.getByText("This link looks incomplete")).toBeInTheDocument();
    expect(unfollow).not.toHaveBeenCalled();
    none.unmount();

    render(<UnsubscribeResult token="tok" />);
    expect(
      await screen.findByText("We couldn't reach the garden"),
    ).toBeInTheDocument();
  });

  it("reads the token from the link's fragment and still accepts the older ?token=", () => {
    expect(tokenFromUrl("#token=tok-frag", "")).toBe("tok-frag");
    expect(tokenFromUrl("", "?token=tok-query")).toBe("tok-query");
    expect(tokenFromUrl("", "")).toBeUndefined();
  });
});
