import type { NextConfig } from "next";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:7860";

const nextConfig: NextConfig = {
  // The FastAPI backend serves the REST API, WebRTC signalling and product images.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
      { source: "/images/:path*", destination: `${BACKEND_URL}/images/:path*` },
    ];
  },
};

export default nextConfig;
