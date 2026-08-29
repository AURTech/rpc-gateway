import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MotionList, MotionListItem } from "./motion-list";

describe("MotionList", () => {
  it("renders items without adding a nesting level", () => {
    // card-grid-view puts the grid classes on MotionList itself, so an extra
    // wrapper would collapse every card into one grid cell.
    const { container } = render(
      <MotionList className="grid grid-cols-2">
        <MotionListItem>one</MotionListItem>
        <MotionListItem>two</MotionListItem>
      </MotionList>,
    );

    const list = container.querySelector('[data-slot="motion-list"]');
    expect(list).not.toBeNull();
    expect(list).toHaveClass("grid", "grid-cols-2");
    expect(list?.children).toHaveLength(2);
    expect(screen.getByText("one")).toBeInTheDocument();
  });

  it("keeps a caller's className on the item, not a wrapper", () => {
    // mobile-data-list hangs its divider shadow off the item element itself.
    const { container } = render(
      <MotionList>
        <MotionListItem className="divider-class">row</MotionListItem>
      </MotionList>,
    );

    const item = container.querySelector('[data-slot="motion-list-item"]');
    expect(item).toHaveClass("divider-class");
    expect(item?.textContent).toBe("row");
  });

  it("tolerates non-item children", () => {
    // The grid's "fetching more" skeleton is a plain child of the list.
    render(
      <MotionList>
        <MotionListItem>row</MotionListItem>
        <div>skeleton</div>
      </MotionList>,
    );

    expect(screen.getByText("skeleton")).toBeInTheDocument();
  });
});

describe("MotionList element", () => {
  it("can render a semantic list so ul > li stays valid", () => {
    // app-networks-panel relies on this: a div between <ul> and <li> would be
    // invalid HTML and would break the parent's divide-y hairlines.
    const { container } = render(
      <MotionList as="ul" className="divide-y">
        <MotionListItem as="li">row</MotionListItem>
      </MotionList>,
    );

    const list = container.querySelector('[data-slot="motion-list"]');
    expect(list?.tagName).toBe("UL");
    expect(list?.firstElementChild?.tagName).toBe("LI");
  });

  it("defaults to div", () => {
    const { container } = render(
      <MotionList>
        <MotionListItem>row</MotionListItem>
      </MotionList>,
    );

    expect(container.querySelector('[data-slot="motion-list"]')?.tagName).toBe(
      "DIV",
    );
  });
});
