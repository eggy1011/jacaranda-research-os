import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
import path from "node:path";

const withNextIntl = createNextIntlPlugin();

const nextConfig: NextConfig = {
  poweredByHeader: false,
  turbopack: {
    root: path.join(process.cwd(), "../.."),
  },
};

export default withNextIntl(nextConfig);
