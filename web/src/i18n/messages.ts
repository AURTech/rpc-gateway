import type { AbstractIntlMessages } from "next-intl";

import auth from "../locales/en/auth.json";
import common from "../locales/en/common.json";
import dashboard from "../locales/en/dashboard.json";

/**
 * i18n contract: English is the console's only language.
 *
 * Every UI string lives in `src/locales/en/*.json`. `common.json` is spread at
 * the root of the message bag; each page bundle is namespaced under its file
 * name, so `dashboard.json` keys resolve as `dashboard.*`.
 */
export const messages = {
  ...common,
  auth,
  dashboard,
} satisfies AbstractIntlMessages;
