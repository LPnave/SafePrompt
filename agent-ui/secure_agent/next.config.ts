import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable React Strict Mode for better development experience
  reactStrictMode: true,

  // Webpack configuration for better hot reload
  webpack: (config, { dev, isServer }) => {
    if (dev && !isServer) {
      // Enable hot module replacement
      config.watchOptions = {
        poll: 1000, // Check for changes every second
        aggregateTimeout: 300, // Delay rebuild after first change
      };
    }
    return config;
  },
};

export default nextConfig;
