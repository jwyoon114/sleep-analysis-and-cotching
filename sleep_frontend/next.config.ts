import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  cacheMaxMemorySize: 0,
  distDir: process.env.SLEEP_NEXT_DIST_DIR || ".next",
  poweredByHeader: false,
  async headers() {
    return [{source:"/sw.js",headers:[{key:"Cache-Control",value:"no-cache, no-store, must-revalidate"},{key:"Service-Worker-Allowed",value:"/"}]}, {
      source: "/downloads/daljam-android.apk",
      headers: [
        {key:"Content-Type",value:"application/vnd.android.package-archive"},
        {key:"Content-Disposition",value:'attachment; filename="daljam-android.apk"'},
        {key:"Cache-Control",value:"public, max-age=0, must-revalidate"},
      ],
    }, { source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "same-origin" },
      { key: "X-Frame-Options", value: "DENY" },
    ] }];
  },
};
export default config;
