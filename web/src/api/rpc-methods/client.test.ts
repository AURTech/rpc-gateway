import { describe, expect, it } from "vitest";

import { jsonResponse, stubFetch } from "@/test/fetch";

import { listRpcMethods } from "./client";

const fetchMock = stubFetch();

describe("rpc methods api client", () => {
  it("parses the method catalog envelope", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        msg: "ok",
        data: {
          items: [
            {
              protocol: "evm",
              protocol_label: "EVM",
              sources: [
                {
                  label: "Ethereum Execution APIs",
                  url: "https://ethereum.github.io/execution-apis/",
                },
              ],
              methods: [
                {
                  value: "debug_traceCall",
                  label: "debug_traceCall",
                  namespace: "debug",
                  namespace_label: "Debug",
                  risk: "sensitive",
                  risk_label: "Sensitive",
                  deprecated: false,
                },
              ],
            },
          ],
        },
      }),
    );

    const result = await listRpcMethods();

    expect(result.items[0].protocol).toBe("evm");
    expect(result.items[0].methods[0]).toMatchObject({
      value: "debug_traceCall",
      risk: "sensitive",
      deprecated: false,
    });
  });

  it("serializes the optional protocol filter", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        msg: "ok",
        data: { items: [] },
      }),
    );

    await listRpcMethods({ protocol: "svm" });

    expect(fetchMock.mock.calls[0][0] as string).toMatch(
      /\/v2\/meta\/jsonrpc-methods\?protocol=svm$/,
    );
  });
});
