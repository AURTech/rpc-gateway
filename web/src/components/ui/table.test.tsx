import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { STAGGER_MAX } from "@/lib/motion";
import { Table, TableBody, TableCell, TableRow } from "./table";

function renderRows(count: number, withStagger: boolean) {
  return render(
    <Table>
      <TableBody>
        {Array.from({ length: count }, (_, i) => i).map((i) => (
          <TableRow key={`row-${i}`} enterIndex={withStagger ? i : undefined}>
            <TableCell>row {i}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>,
  );
}

describe("TableRow entrance stagger", () => {
  it("marks staggered rows and indexes them in order", () => {
    const { container } = renderRows(3, true);

    const rows = container.querySelectorAll('tr[data-enter=""]');
    expect(rows).toHaveLength(3);
    expect(rows[0].getAttribute("style")).toContain("--row-i: 0");
    expect(rows[2].getAttribute("style")).toContain("--row-i: 2");
  });

  it("clamps the index so a long list doesn't push the tail out", () => {
    const { container } = renderRows(STAGGER_MAX + 5, true);

    const rows = container.querySelectorAll('tr[data-enter=""]');
    const last = rows[rows.length - 1];
    expect(last.getAttribute("style")).toContain(`--row-i: ${STAGGER_MAX}`);
  });

  it("leaves rows untouched when no index is given", () => {
    const { container } = renderRows(2, false);

    expect(container.querySelectorAll("tr[data-enter]")).toHaveLength(0);
    expect(container.querySelector("tr")?.getAttribute("style")).toBeNull();
  });

  it("keeps the row role so table queries are unaffected", () => {
    // Guards the assumption the list pages rely on: the stagger adds an
    // attribute, never a wrapper element.
    const { container } = renderRows(4, true);

    expect(container.querySelectorAll('[role="row"], tr')).toHaveLength(4);
  });
});
