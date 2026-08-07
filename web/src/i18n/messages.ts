import type { AbstractIntlMessages } from "next-intl";

const PAGE_NAMESPACES = ["home", "auth", "dashboard"] as const;

/** Load an English message namespace. */
async function loadJson(name: string) {
  try {
    const mod = await import(`../locales/en/${name}.json`);
    return (mod.default ?? mod) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** Load the complete English message bag. */
async function loadBundle(): Promise<Record<string, unknown>> {
  const common = (await loadJson("common")) ?? {};
  const messages: Record<string, unknown> = { ...common };
  for (const ns of PAGE_NAMESPACES) {
    const data = await loadJson(ns);
    if (data) messages[ns] = data;
  }
  return messages;
}

export async function loadMessages(): Promise<AbstractIntlMessages> {
  return (await loadBundle()) as AbstractIntlMessages;
}
