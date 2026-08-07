import { z } from "zod/v4";

import { api } from "@/api/client";

const overviewSchema = z.object({
  endpoint_total: z.number().int(),
  active_endpoint_total: z.number().int(),
  provider_total: z.number().int(),
  app_total: z.number().int(),
});

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type Overview = z.infer<typeof overviewSchema>;

export async function getOverview(): Promise<Overview> {
  const response = await api.get<unknown>("/v2/overview");
  return envelope(overviewSchema).parse(response).data;
}
