import type { NextConfig } from "next";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:7860";
// The hosted demo builds with NEXT_EXPORT=1 and FastAPI serves the static files, so the browser,
// the REST API and the audio websocket all share one origin and nothing needs proxying.
const isExport = process.env.NEXT_EXPORT === "1";

const exportConfig: NextConfig = { output: "export", trailingSlash: true };

const devConfig: NextConfig = {
  // In development the FastAPI backend serves the REST API, WebRTC signalling and product images.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
      { source: "/images/:path*", destination: `${BACKEND_URL}/images/:path*` },
    ];
  },
};

export default (isExport ? exportConfig : devConfig) satisfies NextConfig;
