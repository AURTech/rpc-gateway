// Central font wiring for every document root (<html>) in the app.
// Import this once per <html> entry: it pulls in the self-hosted webfont CSS as
// side effects and re-exports GeistSans, whose `.variable` className defines the
// `--font-geist-sans` custom property consumed by `--font-sans` in globals.css.
//
// - Geist (Latin/UI)         — OFL-1.1, self-hosted via next/font.
// - Maple Mono (mono/code)   — OFL-1.1, weights 400/700.
import { GeistSans } from "geist/font/sans";

import "@fontsource/maple-mono/400.css";
import "@fontsource/maple-mono/700.css";

export { GeistSans };
