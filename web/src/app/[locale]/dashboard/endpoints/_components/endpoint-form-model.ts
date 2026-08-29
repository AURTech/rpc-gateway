import { isApiError } from "@/api/client";
import type {
  EndpointCreateAuth,
  EndpointDetail,
  EndpointProtocol,
  UpdateEndpointInput,
} from "@/api/endpoints/client";
import type { Chain, Network } from "@/lib/blockchain";

interface EndpointFormState {
  name: string;
  chain: Chain;
  network: Network;
  protocol: EndpointProtocol;
  url: string;
  enabled: boolean;
  headerName: string;
  headerValue: string;
}

const EMPTY_ENDPOINT_FORM: EndpointFormState = {
  name: "",
  chain: "ethereum",
  network: "mainnet",
  protocol: "jsonrpc",
  url: "",
  enabled: true,
  headerName: "",
  headerValue: "",
};

function endpointSecret(endpoint: EndpointDetail): string {
  return "secret" in endpoint.auth ? endpoint.auth.secret : "";
}

function endpointUrlFromDetail(endpoint: EndpointDetail): string {
  return endpoint.effective_url ?? endpoint.url;
}

function endpointFormFromDetail(endpoint: EndpointDetail): EndpointFormState {
  const header = (() => {
    switch (endpoint.auth.type) {
      case "bearer":
        return {
          headerName: "Authorization",
          headerValue: `Bearer ${endpointSecret(endpoint)}`,
        };
      case "header_api_key":
        return {
          headerName: endpoint.auth.header_name,
          headerValue: endpointSecret(endpoint),
        };
      default:
        return { headerName: "", headerValue: "" };
    }
  })();

  return {
    name: endpoint.name,
    chain: endpoint.chain,
    network: endpoint.network,
    protocol: endpoint.protocol,
    url: endpointUrlFromDetail(endpoint),
    enabled: endpoint.enabled,
    ...header,
  };
}

function isEndpointHeaderValid(form: EndpointFormState): boolean {
  return Boolean(form.headerName.trim()) === Boolean(form.headerValue.trim());
}

function isValidEndpointUrl(value: string): boolean {
  try {
    const parsed = new URL(value.trim());
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function makeEndpointCreateAuth(form: EndpointFormState): EndpointCreateAuth {
  if (!form.headerName.trim()) return { type: "none" };
  return {
    type: "header_api_key",
    header_name: form.headerName.trim(),
    secret: form.headerValue.trim(),
  };
}

function buildEndpointUpdateInput(
  form: EndpointFormState,
  endpoint: EndpointDetail,
): UpdateEndpointInput {
  const input: UpdateEndpointInput = { expected_version: endpoint.version };
  const providerManaged = endpoint.origin_type === "provider";

  if (form.name.trim() !== endpoint.name) input.name = form.name.trim();
  if (form.enabled !== endpoint.enabled) input.enabled = form.enabled;

  if (!providerManaged) {
    const currentUrl = endpointUrlFromDetail(endpoint);
    const urlChanged = form.url.trim() !== currentUrl;
    if (urlChanged) input.url = form.url.trim();

    const nextAuth = makeEndpointCreateAuth(form);
    const authChanged = (() => {
      if (endpoint.auth.type === "none") return nextAuth.type !== "none";
      if (endpoint.auth.type === "bearer") {
        return !(
          nextAuth.type === "header_api_key" &&
          nextAuth.header_name.toLowerCase() === "authorization" &&
          nextAuth.secret === `Bearer ${endpointSecret(endpoint)}`
        );
      }
      if (endpoint.auth.type === "header_api_key") {
        return !(
          nextAuth.type === "header_api_key" &&
          nextAuth.header_name === endpoint.auth.header_name &&
          nextAuth.secret === endpointSecret(endpoint)
        );
      }
      return nextAuth.type !== "none" || urlChanged;
    })();

    if (authChanged) input.auth = nextAuth;
  }

  return input;
}

function endpointFormHasChanges(
  form: EndpointFormState,
  endpoint: EndpointDetail,
): boolean {
  return Object.keys(buildEndpointUpdateInput(form, endpoint)).some(
    (key) => key !== "expected_version",
  );
}

function isEndpointVersionConflict(error: unknown): boolean {
  return (
    isApiError(error) &&
    error.message.toLowerCase().includes("version conflict")
  );
}

export {
  buildEndpointUpdateInput,
  EMPTY_ENDPOINT_FORM,
  endpointFormFromDetail,
  endpointFormHasChanges,
  isEndpointHeaderValid,
  isEndpointVersionConflict,
  isValidEndpointUrl,
  makeEndpointCreateAuth,
};
export type { EndpointFormState };
