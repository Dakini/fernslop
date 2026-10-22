import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConfirmFollowResult } from "@/routes/confirm-follow";
import { setServices, type GardenService } from "@/services";

const useService = (confirmFollow: GardenService["confirmFollow"]) =>
  setServices({ confirmFollow } as GardenService);

afterEach(() => setServices(null));

// Link needs a router, so stub it out; the page logic is what's under test.
vi.mock("@tanstack/react-router", async (orig) => ({
  ...(await orig<typeof import("@tanstack/react-router")>()),
  Link: ({ children }: { children: React.ReactNode }) => (
    <a href="/">{children}</a>
  ),
}));

describe("confirm follow page", () => {
  it("confirms once with the token and shows confirmed, expired-or-invalid and unreachable", async () => {
    const confirmFollow = vi.fn().mockResolvedValue(true);
    useService(confirmFollow);
    const first = render(<ConfirmFollowResult token="tok-1" />);
    expect(
      await screen.findByText("You're following this garden"),
    ).toBeInTheDocument();
    expect(confirmFollow).toHaveBeenCalledExactlyOnceWith("tok-1");
    first.unmount();

    useService(vi.fn().mockResolvedValue(false));
    const expired = render(<ConfirmFollowResult token="old" />);
    expect(
      await screen.findByText("This link has expired or doesn't work"),
    ).toBeInTheDocument();
    expired.unmount();

    useService(vi.fn().mockRejectedValue(new Error("offline")));
    render(<ConfirmFollowResult token="tok" />);
    expect(
      await screen.findByText("We couldn't reach the garden"),
    ).toBeInTheDocument();
  });
});
