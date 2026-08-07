import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Endpoint } from "@/api/endpoints/client";
import { makeEndpoint } from "@/test/fixtures";

import { EndpointPoolField } from "./endpoint-pool-field";

// next-intl is stubbed to echo the key, so labels assert as `form.moveUp`,
// `endpointTable.toggleLabel`, etc. Interpolated values are appended so the
// per-row accessible names stay distinguishable.
vi.mock("next-intl", async () =>
  (await import("@/test/intl")).nextIntlMock({ separator: " " }),
);

const useEndpointsQuery = vi.fn();
vi.mock("@/hooks/use-endpoints", () => ({
  useEndpointsQuery: (...args: unknown[]) => useEndpointsQuery(...args),
}));

vi.mock("../../endpoints/_components/new-endpoint-button", () => ({
  NewEndpointButton: ({
    className,
    initialChain,
    initialNetwork,
    initialProtocol,
    label,
    presentation,
    showIcon,
  }: {
    className?: string;
    initialChain: string;
    initialNetwork: string;
    initialProtocol: string;
    label: string;
    presentation?: "dialog" | "sheet";
    showIcon?: boolean;
  }) => (
    <button
      type="button"
      className={className}
      data-chain={initialChain}
      data-network={initialNetwork}
      data-protocol={initialProtocol}
      data-presentation={presentation}
      data-show-icon={showIcon}
    >
      {label}
    </button>
  ),
}));

vi.mock("../../endpoints/_components/delete-endpoint-dialog", () => ({
  DeleteEndpointDialog: ({
    endpoint,
    open,
    onDeleted,
  }: {
    endpoint: Endpoint | null;
    open: boolean;
    onDeleted?: (id: string) => void;
  }) =>
    open && endpoint ? (
      <div role="dialog">
        <span>{`delete ${endpoint.name}`}</span>
        <button type="button" onClick={() => onDeleted?.(endpoint.id)}>
          confirm delete
        </button>
      </div>
    ) : null,
}));

function endpointNamed(id: string, name: string): Endpoint {
  return makeEndpoint({ id, name, url: `https://${name}.example.test` });
}

const ALPHA = endpointNamed("ep_alpha", "alpha");
const BRAVO = endpointNamed("ep_bravo", "bravo");
const CHARLIE = endpointNamed("ep_charlie", "charlie");

function renderField(
  props: Partial<React.ComponentProps<typeof EndpointPoolField>> = {},
  items: Endpoint[] = [ALPHA, BRAVO, CHARLIE],
) {
  useEndpointsQuery.mockReturnValue({
    data: { items },
    isLoading: false,
    isError: false,
  });
  const onChange = vi.fn();
  const onWeightChange = vi.fn();
  render(
    <EndpointPoolField
      chain="ethereum"
      network="mainnet"
      title="Default endpoints"
      value={[ALPHA.id, BRAVO.id]}
      onChange={onChange}
      onWeightChange={onWeightChange}
      {...props}
    />,
  );
  return { onChange, onWeightChange };
}

/** Body rows only — the header row is excluded. */
function bodyRows() {
  const table = screen.getByRole("table");
  const body = within(table).getAllByRole("rowgroup")[1];
  return within(body).getAllByRole("row");
}

function toggleFor(name: string) {
  return screen.getByRole("switch", {
    name: `endpointTable.toggleLabel ${name}`,
  });
}

describe("EndpointPoolField", () => {
  it("renders no disconnected placeholder while endpoints load", () => {
    useEndpointsQuery.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });

    const { container } = render(
      <EndpointPoolField
        chain="ethereum"
        network="mainnet"
        title="Default endpoints"
        value={[]}
        onChange={() => {}}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("heads the group with the caller's title, below the section h2 tier", () => {
    renderField({ title: "Rule endpoints", description: "for these methods" });

    expect(
      screen.getByRole("heading", { level: 3, name: "Rule endpoints" }),
    ).toBeInTheDocument();
    expect(screen.getByText("for these methods")).toBeInTheDocument();
  });

  it("replaces the attached count with a contextual create endpoint action", () => {
    renderField();

    const create = screen.getByRole("button", {
      name: "endpointTable.createEndpoint",
    });
    expect(create).toHaveAttribute("data-chain", "ethereum");
    expect(create).toHaveAttribute("data-network", "mainnet");
    expect(create).toHaveAttribute("data-protocol", "jsonrpc");
    expect(create).toHaveAttribute("data-presentation", "dialog");
    expect(create).toHaveAttribute("data-show-icon", "false");
    expect(create).toHaveClass("rounded-xl");
    expect(
      screen.queryByText(/endpointTable\.poolCount/),
    ).not.toBeInTheDocument();
  });

  it("queries and creates endpoints for the selected protocol", () => {
    renderField({ protocol: "http_api" });

    expect(useEndpointsQuery).toHaveBeenCalledWith(
      expect.objectContaining({ protocol: "http_api" }),
    );
    expect(
      screen.getByRole("button", { name: "endpointTable.createEndpoint" }),
    ).toHaveAttribute("data-protocol", "http_api");
  });

  it("lists every endpoint in one table, assigned ones first", () => {
    renderField();

    const rows = bodyRows();
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("alpha")).toBeInTheDocument();
    expect(within(rows[1]).getByText("bravo")).toBeInTheDocument();
    expect(within(rows[2]).getByText("charlie")).toBeInTheDocument();

    // Single view — no tabs to switch between assigned and available.
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("reflects assignment in each row's switch", () => {
    renderField();

    expect(toggleFor("alpha")).toBeChecked();
    expect(toggleFor("bravo")).toBeChecked();
    expect(toggleFor("charlie")).not.toBeChecked();
  });

  it("assigns an endpoint by switching its row on", async () => {
    const { onChange } = renderField();

    await userEvent.click(toggleFor("charlie"));

    expect(onChange).toHaveBeenCalledWith([ALPHA.id, BRAVO.id, CHARLIE.id]);
  });

  it("unassigns an endpoint by switching its row off", async () => {
    const { onChange } = renderField();

    await userEvent.click(toggleFor("alpha"));

    expect(onChange).toHaveBeenCalledWith([BRAVO.id]);
  });

  it("opens endpoint deletion from a row and removes it from the draft", async () => {
    const { onChange } = renderField();

    await userEvent.click(
      screen.getByRole("button", { name: "endpointTable.deleteLabel alpha" }),
    );

    expect(screen.getByRole("dialog")).toHaveTextContent("delete alpha");
    await userEvent.click(
      screen.getByRole("button", { name: "confirm delete" }),
    );
    expect(onChange).toHaveBeenCalledWith([BRAVO.id]);
  });

  it("disables the reorder controls on unassigned rows", () => {
    renderField();

    expect(
      screen.getByRole("button", { name: "form.moveDown alpha" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "form.moveUp charlie" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "form.moveDown charlie" }),
    ).toBeDisabled();
  });

  it("omits the weight column when unweighted", () => {
    renderField();

    expect(
      screen.queryByRole("columnheader", { name: /weights.relativeColumn/ }),
    ).not.toBeInTheDocument();
    expect(within(bodyRows()[0]).getAllByRole("cell")).toHaveLength(4);
  });

  it("replaces the priority column with weight and share when weighted", () => {
    renderField({
      weighted: true,
      weights: { [ALPHA.id]: 3, [BRAVO.id]: 1 },
    });

    expect(
      screen.getByRole("columnheader", { name: /weights.relativeColumn/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: "endpointTable.priority" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "form.moveDown alpha" }),
    ).not.toBeInTheDocument();

    const cells = within(bodyRows()[0]).getAllByRole("cell");
    expect(cells).toHaveLength(4);
    // 3 of 4 total → 75%.
    expect(within(cells[1]).getByText("weights.share 75")).toBeInTheDocument();
  });

  it("leaves the weight input inert on unassigned rows", () => {
    renderField({
      weighted: true,
      weights: { [ALPHA.id]: 3, [BRAVO.id]: 1 },
    });

    expect(
      screen.getByRole("textbox", { name: "weights.relativeInputLabel alpha" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("textbox", {
        name: "weights.relativeInputLabel charlie",
      }),
    ).toBeDisabled();
  });

  it("reports weight edits through onWeightChange", async () => {
    const { onWeightChange } = renderField({
      weighted: true,
      weights: { [ALPHA.id]: 3, [BRAVO.id]: 1 },
    });

    const input = screen.getByRole("textbox", {
      name: "weights.relativeInputLabel alpha",
    });
    await userEvent.type(input, "5");

    expect(onWeightChange).toHaveBeenCalledWith(ALPHA.id, 35);
  });

  it("reorders assigned endpoints", async () => {
    const { onChange } = renderField();

    await userEvent.click(
      screen.getByRole("button", { name: "form.moveDown alpha" }),
    );

    expect(onChange).toHaveBeenCalledWith([BRAVO.id, ALPHA.id]);
  });

  it("shows the empty label spanning every column", () => {
    renderField({ value: [], weighted: true }, []);

    const cell = screen.getByRole("cell", { name: "endpointTable.empty" });
    expect(cell).toHaveAttribute("colspan", "4");
  });
});
