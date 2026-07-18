import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle (.next/standalone) so the Docker
  // runtime image is small and doesn't need the full node_modules tree.
  output: "standalone",
};

export default nextConfig;
