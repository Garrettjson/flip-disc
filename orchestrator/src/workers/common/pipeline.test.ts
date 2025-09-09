import { describe, test, expect } from "bun:test";
import { packRows, type Rows } from "./pipeline";

describe("Worker Pipeline", () => {
  test("packs rows into binary format", () => {
    const rows: Rows = [
      [1, 0],
      [0, 1]
    ];
    
    const packed = packRows(rows);
    expect(packed.length).toBe(1);
    expect(packed[0]).toBe(0x90); // 10010000 in binary
  });
  
  test("handles empty rows", () => {
    const packed = packRows([]);
    expect(packed.length).toBe(0);
  });
});