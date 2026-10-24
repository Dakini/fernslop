import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { setServices, type GardenService, type Plant } from "@/services";
import { AddPlantDialog, MISS_AFTER_MS } from "./AddPlantDialog";

vi.mock("@/lib/image", () => ({ prepareImage: async (file: File) => file }));

afterEach(() => {
  vi.restoreAllMocks();
  setServices(null);
});

const BASIL = { id: "basil", common_name: "Basil", scientific_name: "Ocimum basilicum", category: "herb" } as Plant;

function setup() {
  const searchPlants = vi.fn(async (q: string) => ("basil".includes(q.toLowerCase()) ? [BASIL] : []));
  const recordSearchMiss = vi.fn(async () => undefined);
  setServices({ searchPlants, recordSearchMiss } as unknown as GardenService);
  const onOpenChange = vi.fn();
  render(<AddPlantDialog open onOpenChange={onOpenChange} onPick={vi.fn()} />);
  const input = screen.getByPlaceholderText(/Basil/);
  const typeAndSettle = async (text: string) => {
    fireEvent.change(input, { target: { value: text } });
    await waitFor(() => expect(searchPlants).toHaveBeenLastCalledWith(text));
    await screen.findByText(text && !"basil".includes(text) ? `No plants match “${text}”.` : "Basil");
  };
  return { input, onOpenChange, recordSearchMiss, typeAndSettle };
}

describe("AddPlantDialog search misses", () => {
  it("reports a miss once the person stops typing, and only the term they stopped on", async () => {
    const { recordSearchMiss, typeAndSettle } = setup();

    // Each of these finds nothing, but the next keystroke comes before the pause is up
    await typeAndSettle("k");
    await typeAndSettle("ka");
    await typeAndSettle("kale");
    expect(recordSearchMiss).not.toHaveBeenCalled();

    await waitFor(() => expect(recordSearchMiss).toHaveBeenCalledWith("kale"), { timeout: MISS_AFTER_MS + 1000 });
    expect(recordSearchMiss).toHaveBeenCalledTimes(1);
  });

  it("reports a miss on Enter before the pause is up, and only once per term", async () => {
    const { input, recordSearchMiss, typeAndSettle } = setup();

    await typeAndSettle("ka");
    await typeAndSettle("kale");
    expect(recordSearchMiss).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(recordSearchMiss).toHaveBeenCalledTimes(1);
    expect(recordSearchMiss).toHaveBeenCalledWith("kale");
  });

  it("reports a miss on closing the dialog, but not a term that found plants", async () => {
    const { onOpenChange, recordSearchMiss, typeAndSettle } = setup();

    await typeAndSettle("bas");
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(recordSearchMiss).not.toHaveBeenCalled();
  });

  it("reports a miss on switching to the Photo tab", async () => {
    const { recordSearchMiss, typeAndSettle } = setup();

    await typeAndSettle("kale");
    const photo = screen.getByRole("tab", { name: /Photo/ });
    fireEvent.mouseDown(photo);
    fireEvent.click(photo);

    await screen.findByText("Upload a photo");
    expect(recordSearchMiss).toHaveBeenCalledWith("kale");
  });

  it("hides the low-confidence notice when the person goes back to the Photo tab", async () => {
    const identifyPlant = vi.fn(async () => [{ plant: BASIL, confidence: 0.1 }]);
    const searchPlants = vi.fn(async () => [BASIL]);
    setServices({ searchPlants, identifyPlant, recordSearchMiss: vi.fn() } as unknown as GardenService);
    render(<AddPlantDialog open onOpenChange={vi.fn()} onPick={vi.fn()} />);
    const photoTab = () => {
      const tab = screen.getByRole("tab", { name: /Photo/ });
      fireEvent.mouseDown(tab);
      fireEvent.click(tab);
    };

    photoTab();
    const file = new File(["x"], "leaf.png", { type: "image/png" });
    fireEvent.change(await screen.findByLabelText(/Upload a photo/), { target: { files: [file] } });
    expect(await screen.findByRole("status")).toHaveTextContent("try searching instead");

    photoTab();
    await screen.findByText("Upload a photo");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
