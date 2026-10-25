import { describe, expect, it } from "vitest";

import { sortRows } from "../../src/lib/sort";

const rows = [
  { id: 1, name: "Zacian", cp: 2183 },
  { id: 2, name: "Énamorus", cp: null },
  { id: 3, name: "Mewtwo", cp: 3076 },
  { id: 4, name: "abra", cp: 2183 },
];
const columns = { name: (r: (typeof rows)[number]) => r.name, cp: (r: (typeof rows)[number]) => r.cp };

describe("sortRows", () => {
  it("sorts numbers both ways, keeps ties in order and puts unknown values last", () => {
    expect(sortRows(rows, "-cp", columns).map((r) => r.id)).toEqual([3, 1, 4, 2]);
    expect(sortRows(rows, "cp", columns).map((r) => r.id)).toEqual([1, 4, 3, 2]);
  });

  it("sorts text the Dutch way, ignoring case and accents", () => {
    expect(sortRows(rows, "name", columns).map((r) => r.name)).toEqual(["abra", "Énamorus", "Mewtwo", "Zacian"]);
  });

  it("leaves the list as it is for an unknown column", () => {
    expect(sortRows(rows, "-geheim", columns)).toEqual(rows);
  });
});
