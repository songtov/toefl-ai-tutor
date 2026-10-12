import type { NextConfig } from "next";

const apiUrl = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // The app is opened at 127.0.0.1 (the OAuth redirect host), so dev HMR must accept it.
  allowedDevOrigins: ["127.0.0.1"],
  experimental: {
    // Scoring and correction run two LLM calls back to back.
    proxyTimeout: 120_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
