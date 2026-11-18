import type { NextConfig } from "next";

// Pages read the signed-in user from cookies, so they render per request.
const nextConfig: NextConfig = {
  cacheComponents: false,
};

export default nextConfig;
