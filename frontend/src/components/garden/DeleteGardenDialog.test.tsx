import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";
import { setServices, type GardenService } from "@/services";
import { DeleteGardenDialog } from "./DeleteGardenDialog";

afterEach(() => {
  vi.restoreAllMocks();
  setServices(null);
});

function setup(deleteRoom: GardenService["deleteRoom"]) {
  setServices({ deleteRoom } as GardenService);
  const onDeleted = vi.fn();
  render(
    <DeleteGardenDialog
      roomId="r1"
      roomName="Elm Street"
      onDeleted={onDeleted}
    />,
  );
  return { onDeleted };
}

describe("DeleteGardenDialog", () => {
  it("names the garden, focuses Cancel, disables Delete while pending, then reports the deletion", async () => {
    let finish!: (v: boolean) => void;
    const deleteRoom = vi.fn(() => new Promise<boolean>((r) => (finish = r)));
    const { onDeleted } = setup(deleteRoom);

    fireEvent.click(screen.getByRole("button", { name: "Delete garden" }));
    expect(await screen.findByText(/Elm Street/)).toBeInTheDocument();
    expect(screen.getByText(/cannot be undone/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();

    fireEvent.click(screen.getByRole("button", { name: "Delete garden" }));
    expect(
      screen.getByRole("button", { name: "Delete garden" }),
    ).toBeDisabled();
    expect(deleteRoom).toHaveBeenCalledTimes(1);
    expect(deleteRoom).toHaveBeenCalledWith("r1");
    expect(onDeleted).not.toHaveBeenCalled();

    finish(true); // 204, also when someone else deleted it first
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
  });

  it("keeps the dialog open with an error toast when deleting fails, and lets the user retry", async () => {
    const error = vi.spyOn(toast, "error").mockImplementation(() => 1);
    const deleteRoom = vi
      .fn()
      .mockRejectedValueOnce(new Error("Server down"))
      .mockResolvedValue(true);
    const { onDeleted } = setup(deleteRoom);

    fireEvent.click(screen.getByRole("button", { name: "Delete garden" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Delete garden" }),
    );
    await waitFor(() => expect(error).toHaveBeenCalledWith("Server down"));
    expect(onDeleted).not.toHaveBeenCalled();
    const confirm = screen.getByRole("button", { name: "Delete garden" });
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(confirm).toBeEnabled();

    fireEvent.click(confirm);
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
  });

  it("closes without deleting when the overlay is clicked, but not while the request is pending", async () => {
    let finish!: (v: boolean) => void;
    const deleteRoom = vi.fn(() => new Promise<boolean>((r) => (finish = r)));
    const { onDeleted } = setup(deleteRoom);
    const overlay = () =>
      document.body.querySelector<HTMLElement>(".bg-black\\/80")!;

    fireEvent.click(screen.getByRole("button", { name: "Delete garden" }));
    await screen.findByRole("alertdialog");
    fireEvent.click(overlay());
    await waitFor(() =>
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(),
    );
    expect(deleteRoom).not.toHaveBeenCalled();
    expect(onDeleted).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Delete garden" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Delete garden" }),
    );
    fireEvent.click(overlay()); // request in flight: stays open
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    finish(true);
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
  });
});
