import { fireEvent, render, screen } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  BulkDeleteEndpointResult,
  Endpoint,
} from "@/api/endpoints/client";

import { makeEndpoint } from "@/test/fixtures";

import { BulkDeleteEndpointsDialog } from "./bulk-delete-endpoints-dialog";

const { mutationMock } = vi.hoisted(() => ({
  mutationMock: vi.fn(),
}));

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

vi.mock("@/hooks/use-endpoints", () => ({
  useBulkDeleteEndpointsMutation: () => ({
    isPending: false,
    mutate: mutationMock,
  }),
}));

const endpoint = (id: string): Endpoint => makeEndpoint({ id, name: id });

afterEach(() => vi.clearAllMocks());

describe("BulkDeleteEndpointsDialog", () => {
  it("submits selected ids and reports a partial deletion", () => {
    const result: BulkDeleteEndpointResult = {
      total: 2,
      deleted: [{ id: "endpoint-1", version: 2, deleted: true }],
      referenced_ids: ["endpoint-2"],
    };
    const completed = vi.fn();
    const openChange = vi.fn();
    mutationMock.mockImplementationOnce(
      (
        _ids: readonly string[],
        options: { onSuccess: (value: BulkDeleteEndpointResult) => void },
      ) => options.onSuccess(result),
    );

    render(
      <BulkDeleteEndpointsDialog
        endpoints={[endpoint("endpoint-1"), endpoint("endpoint-2")]}
        open
        onOpenChange={openChange}
        onCompleted={completed}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "bulk.dialog.confirm" }),
    );

    expect(mutationMock).toHaveBeenCalledWith(
      ["endpoint-1", "endpoint-2"],
      expect.any(Object),
    );
    expect(vi.mocked(toast.warning)).toHaveBeenCalledWith("bulk.toast.partial");
    expect(completed).toHaveBeenCalledWith(result);
    expect(openChange).toHaveBeenCalledWith(false);
  });
});
