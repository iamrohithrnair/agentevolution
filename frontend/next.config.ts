import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts"],
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "*.basemaps.cartocdn.com" },
      { protocol: "https", hostname: "tile.openstreetmap.org" },
    ],
  },
  // The Mongo driver pulls in a few optional native deps; mark them external for the server bundle
  serverExternalPackages: ["mongodb"],
};

export default nextConfig;
