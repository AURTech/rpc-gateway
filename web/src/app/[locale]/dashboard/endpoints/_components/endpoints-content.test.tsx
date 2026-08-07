import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  BulkDeleteEndpointResult,
  Endpoint,
} from "@/api/endpoints/client";
import { makeEndpoint } from "@/test/fixtures";
import { createTestQueryClient, renderWithQuery } from "@/test/query";

import { EndpointsContent } from "./endpoints-content";

const { listEndpointsMock } = vi.hoisted(() => ({
  listEndpointsMock: vi.fn(),
}));

vi.mock("next-intl", async () =>
  (await import("@/test/intl")).nextIntlMock({ separator: ":" }),
);

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock(),
);

vi.mock("@/api/endpoints/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/endpoints/client")>()),
  listEndpoints: listEndpointsMock,
}));

vi.mock("@/hooks/use-media-query", () => ({
  useIsDesktop: () => true,
}));

vi.mock("@/hooks/use-providers", () => ({
  useProviderQuery: () => ({ data: null }),
}));

type ListViewProps = {
  items: readonly Endpoint[];
  tableHeader: ReactNode;
  renderRow: (endpoint: Endpoint) => ReactNode;
  filter?: ReactNode;
  pagination?: { onPageChange: (page: number) => void };
};

vi.mock("@/components/patterns/responsive-list-view", () => ({
  ResponsiveListView: (props: ListViewProps) => (
    <div>
      <table>
        {props.tableHeader}
        <tbody>{props.items.map(props.renderRow)}</tbody>
      </table>
      {props.filter}
      <button type="button" onClick={() => props.pagination?.onPageChange(2)}>
        next page
      </button>
    </div>
  ),
}));

vi.mock("./endpoint-detail-sheet", () => ({
  EndpointDetailSheet: () => null,
}));
vi.mock("./edit-endpoint-sheet", () => ({ EditEndpointSheet: () => null }));
vi.mock("./delete-endpoint-dialog", () => ({
  DeleteEndpointDialog: () => null,
}));
vi.mock("./endpoint-audit-dialog", () => ({
  EndpointAuditDialog: () => null,
}));
vi.mock("./bulk-delete-endpoints-dialog", () => ({
  BulkDeleteEndpointsDialog: ({
    endpoints,
    open,
    onCompleted,
  }: {
    endpoints: readonly Endpoint[];
    open: boolean;
    onCompleted: (result: BulkDeleteEndpointResult) => void;
  }) =>
    open ? (
      <button
        type="button"
        onClick={() =>
          onCompleted({
            total: endpoints.length,
            deleted: [{ id: endpoints[0].id, version: 2, deleted: true }],
            referenced_ids: [endpoints[1].id],
          })
        }
      >
        complete bulk delete
      </button>
    ) : null,
}));

const endpoint = (id: string): Endpoint => makeEndpoint({ id, name: id });

function EndpointsContentHarness({
  origin,
}: {
  origin: "manual" | "provider";
}) {
  const [selectedById, setSelectedById] = useState<Map<string, Endpoint>>(
    () => new Map(),
  );
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);

  return (
    <>
      <output aria-label="selection count">{selectedById.size}</output>
      {selectedById.size > 0 ? (
        <button type="button" onClick={() => setBulkDeleteOpen(true)}>
          open bulk delete
        </button>
      ) : null}
      <EndpointsContent
        origin={origin}
        selectedById={selectedById}
        setSelectedById={setSelectedById}
        bulkDeleteOpen={bulkDeleteOpen}
        onBulkDeleteOpenChange={setBulkDeleteOpen}
      />
    </>
  );
}

afterEach(() => vi.clearAllMocks());

describe("EndpointsContent bulk deletion", () => {
  it("selects rows and retains only referenced endpoints after completion", async () => {
    listEndpointsMock.mockResolvedValue({
      page: 1,
      size: 12,
      total: 2,
      max_page: 1,
      items: [endpoint("endpoint-1"), endpoint("endpoint-2")],
    });
    const queryClient = createTestQueryClient();

    renderWithQuery(<EndpointsContentHarness origin="manual" />, queryClient);

    const rowSelections = await screen.findAllByRole("checkbox", {
      name: /bulk.selectEndpoint/,
    });
    fireEvent.click(rowSelections[0]);
    fireEvent.click(rowSelections[1]);

    expect(
      screen.getByRole("status", { name: "selection count" }),
    ).toHaveTextContent("2");
    fireEvent.click(screen.getByRole("button", { name: "open bulk delete" }));
    fireEvent.click(
      screen.getByRole("button", { name: "complete bulk delete" }),
    );

    await waitFor(() =>
      expect(
        screen.getByRole("status", { name: "selection count" }),
      ).toHaveTextContent("1"),
    );
    expect(rowSelections[0]).not.toBeChecked();
    expect(rowSelections[1]).toBeChecked();
  });

  it("does not expose bulk selection for provider endpoints", async () => {
    listEndpointsMock.mockResolvedValue({
      page: 1,
      size: 12,
      total: 1,
      max_page: 1,
      items: [{ ...endpoint("endpoint-1"), origin_type: "provider" }],
    });
    const queryClient = createTestQueryClient();

    renderWithQuery(<EndpointsContentHarness origin="provider" />, queryClient);

    await waitFor(() => expect(listEndpointsMock).toHaveBeenCalled());
    expect(
      screen.queryByRole("checkbox", { name: /bulk.selectEndpoint/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "open bulk delete" }),
    ).not.toBeInTheDocument();
  });

  it("clears selections from every page when all shown endpoints are selected", async () => {
    listEndpointsMock.mockImplementation(async ({ page = 1 }) => ({
      page,
      size: 12,
      total: 2,
      max_page: 2,
      items: [endpoint(`endpoint-${page}`)],
    }));
    const queryClient = createTestQueryClient();

    renderWithQuery(<EndpointsContentHarness origin="manual" />, queryClient);

    fireEvent.click(
      await screen.findByRole("checkbox", {
        name: "bulk.selectEndpoint:endpoint-1",
      }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("status", { name: "selection count" }),
      ).toHaveTextContent("1"),
    );

    fireEvent.click(screen.getByRole("button", { name: "next page" }));
    fireEvent.click(
      await screen.findByRole("checkbox", {
        name: "bulk.selectEndpoint:endpoint-2",
      }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("status", { name: "selection count" }),
      ).toHaveTextContent("2"),
    );

    fireEvent.click(
      screen.getByRole("checkbox", { name: "bulk.clearSelection" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("status", { name: "selection count" }),
      ).toHaveTextContent("0"),
    );
    expect(
      screen.queryByRole("button", { name: "open bulk delete" }),
    ).not.toBeInTheDocument();
  });
});
