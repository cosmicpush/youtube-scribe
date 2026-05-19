import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    // Raise the body buffer cap for the /api proxy so uploaded videos
    // aren't truncated at the default 10MB and the backend doesn't see
    // a socket hang up. Next buffers the body in memory, so this also
    // caps per-request RAM.
    proxyClientMaxBodySize: "5gb",
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "i.ytimg.com" },
      { protocol: "https", hostname: "img.youtube.com" },
    ],
  },
  rewrites: async () => [
    {
      source: "/api/:path*",
      destination: "http://localhost:8000/api/:path*",
    },
  ],
};

export default nextConfig;
