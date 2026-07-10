import type { NextConfig } from "next";

const backendUrl =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_SANITIZER_API_URL ||
  "http://localhost:8003";

const nextConfig: NextConfig = {
  reactStrictMode: true,

  // Standalone output for efficient Docker images
  output: "standalone",

  // Proxy admin/report API calls through Next.js (same-origin) to avoid CORS issues
  async rewrites() {
    return [
      {
        source: "/api/reports/:path*",
        destination: `${backendUrl}/api/reports/:path*`,
      },
      {
        source: "/api/admin/:path*",
        destination: `${backendUrl}/api/admin/:path*`,
      },
      {
        source: "/api/threads/:path*",
        destination: `${backendUrl}/api/threads/:path*`,
      },
    ];
  },

  webpack: (config, { dev, isServer }) => {
    if (dev && !isServer) {
      config.watchOptions = {
        poll: 1000,
        aggregateTimeout: 300,
      };
    }
    return config;
  },
};

export default nextConfig;
