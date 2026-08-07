import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useTableController } from "./use-table-controller";

type Col = "name" | "chain" | "state";
const ALL: readonly Col[] = ["name", "chain", "state"];

describe("useTableController", () => {
  it("starts with sensible defaults", () => {
    const { result } = renderHook(() =>
      useTableController<Col>({ allColumns: ALL, initialSort: "created-desc" }),
    );
    expect(result.current.query).toBe("");
    expect(result.current.page).toBe(1);
    expect(result.current.sort).toBe("created-desc");
    expect([...result.current.visibleColumns].sort()).toEqual([...ALL].sort());
    expect(result.current.expanded.size).toBe(0);
  });

  it("resets page to 1 when query or sort changes", () => {
    const { result } = renderHook(() =>
      useTableController<Col>({ allColumns: ALL }),
    );
    act(() => result.current.setPage(4));
    expect(result.current.page).toBe(4);

    act(() => result.current.setQuery("eth"));
    expect(result.current.query).toBe("eth");
    expect(result.current.page).toBe(1);

    act(() => result.current.setPage(3));
    act(() => result.current.setSort("modified-asc"));
    expect(result.current.sort).toBe("modified-asc");
    expect(result.current.page).toBe(1);
  });

  it("resetPage returns to page 1 (for domain filter changes)", () => {
    const { result } = renderHook(() =>
      useTableController<Col>({ allColumns: ALL }),
    );
    act(() => result.current.setPage(5));
    act(() => result.current.resetPage());
    expect(result.current.page).toBe(1);
  });

  it("enforces at least one visible column", () => {
    const { result } = renderHook(() =>
      useTableController<Col>({ allColumns: ALL }),
    );
    act(() => result.current.setVisibleColumns(new Set<Col>(["name"])));
    expect([...result.current.visibleColumns]).toEqual(["name"]);
    expect(result.current.isColumnVisible("name")).toBe(true);
    expect(result.current.isColumnVisible("chain")).toBe(false);

    // Empty set is ignored — the last column stays.
    act(() => result.current.setVisibleColumns(new Set<Col>()));
    expect([...result.current.visibleColumns]).toEqual(["name"]);
  });

  it("toggles row expansion", () => {
    const { result } = renderHook(() =>
      useTableController<Col>({ allColumns: ALL }),
    );
    act(() => result.current.toggleExpanded("row-1"));
    expect(result.current.isExpanded("row-1")).toBe(true);
    act(() => result.current.toggleExpanded("row-1"));
    expect(result.current.isExpanded("row-1")).toBe(false);
  });

  it("only keeps one row expanded at a time", () => {
    const { result } = renderHook(() =>
      useTableController<Col>({ allColumns: ALL }),
    );
    act(() => result.current.toggleExpanded("row-1"));
    act(() => result.current.toggleExpanded("row-2"));
    expect(result.current.isExpanded("row-1")).toBe(false);
    expect(result.current.isExpanded("row-2")).toBe(true);
    expect(result.current.expanded.size).toBe(1);
  });

  it("collapses the open row when the page changes", () => {
    const { result } = renderHook(() =>
      useTableController<Col>({ allColumns: ALL }),
    );
    act(() => result.current.toggleExpanded("row-1"));
    expect(result.current.isExpanded("row-1")).toBe(true);
    act(() => result.current.setPage(2));
    expect(result.current.expanded.size).toBe(0);
  });
});
