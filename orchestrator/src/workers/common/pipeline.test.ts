import { describe, test, expect } from "bun:test";
import { packRows, type Rows } from "./pipeline";

describe("Worker Pipeline", () => {
  test("packs rows into binary format (row stride)", () => {
    const rows: Rows = [
      [1, 0],
      [0, 1]
    ];
    
    const packed = packRows(rows);
    // width=2 -> stride=1 byte per row; height=2 -> total 2 bytes
    expect(packed.length).toBe(2);
    expect(packed[0]).toBe(0x80); // row0: 10 -> 10000000
    expect(packed[1]).toBe(0x40); // row1: 01 -> 01000000
  });
  
  test("handles empty rows", () => {
    const packed = packRows([]);
    expect(packed.length).toBe(0);
  });
});
