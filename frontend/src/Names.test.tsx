import { describe, expect, it } from "vitest";
import { shortName } from "./Names";

describe("shortName", () => {
  it("drops legal endings and fixes all-caps names", () => {
    expect(shortName("NVIDIA CORP")).toBe("Nvidia");
    expect(shortName("Palo Alto Networks, Inc.")).toBe("Palo Alto Networks");
    expect(shortName("CATERPILLAR INC")).toBe("Caterpillar");
    expect(shortName("Shell plc")).toBe("Shell");
  });
});
