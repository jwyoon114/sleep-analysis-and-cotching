import type { NextConfig } from "next";

const config: NextConfig = {
  distDir: process.env.SLEEP_NEXT_DIST_DIR || ".next",
  poweredByHeader: false,
  async headers() {
    return [{source:"/sw.js",headers:[{key:"Cache-Control",value:"no-cache, no-store, must-revalidate"},{key:"Service-Worker-Allowed",value:"/"}]},{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "same-origin" },
      { key: "X-Frame-Options", value: "DENY" },
    ] }];
  },
};
export default config;
