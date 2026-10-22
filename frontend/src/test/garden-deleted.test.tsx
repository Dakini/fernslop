import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRoomLive } from "@/lib/queries";
import { GardenDeleted } from "@/routes/r.$roomId";
import { setServices, type GardenService } from "@/services";

afterEach(() => setServices(null));

// Link needs a router, so stub it out; the page logic is what's under test.
vi.mock("@tanstack/react-router", async (orig) => ({
  ...(await orig<typeof import("@tanstack/react-router")>()),
  Link: ({ children }: { children: React.ReactNode }) => (
    <a href="/">{children}</a>
  ),
}));

describe("deleted garden view", () => {
  it("tells the visitor the garden was deleted and closes the live subscription once the room is gone", () => {
    render(<GardenDeleted />);
    expect(screen.getByText("This garden was deleted")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All gardens" })).toHaveAttribute(
      "href",
      "/",
    );

    const off = vi.fn();
    const subscribe = vi.fn(() => off);
    setServices({ subscribe } as unknown as GardenService);
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={new QueryClient()}>
        {children}
      </QueryClientProvider>
    );
    const { rerender } = renderHook(({ on }) => useRoomLive("r1", on), {
      wrapper,
      initialProps: { on: true },
    });
    expect(subscribe).toHaveBeenCalledTimes(1);
    rerender({ on: false });
    expect(off).toHaveBeenCalledTimes(1);
    expect(subscribe).toHaveBeenCalledTimes(1);
  });
});
