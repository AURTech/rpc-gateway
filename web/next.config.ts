import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
import { validateProductionBuildEnvironment } from "./src/lib/build-env";
import {
  FIXED_SECURITY_HEADERS,
  HSTS_HEADER,
} from "./src/lib/security-headers";

if (process.env.NODE_ENV === "production") {
  validateProductionBuildEnvironment(process.env);
}

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  poweredByHeader: false,
  experimental: {
    globalNotFound: true,
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          ...FIXED_SECURITY_HEADERS,
          ...(process.env.NODE_ENV === "production" ? [HSTS_HEADER] : []),
        ],
      },
    ];
  },
};

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

export default withNextIntl(nextConfig);
