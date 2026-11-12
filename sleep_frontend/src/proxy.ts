import {NextRequest, NextResponse} from "next/server";
import {demoBlockedResponse, isDemoOnly} from "@/lib/demo-mode";

export function proxy(request: NextRequest) {
  if (!isDemoOnly()) return NextResponse.next();
  const path = request.nextUrl.pathname;
  // Deny the entire API namespace, including future routes, before reading bodies.
  if ((path === "/api" || path.startsWith("/api/")) && path !== "/api/demo-health") {
    return demoBlockedResponse();
  }
  if (path === "/" && request.nextUrl.searchParams.get("demo") !== "1") {
    const url = request.nextUrl.clone();
    url.search = "?demo=1";
    const response = NextResponse.redirect(url);
    response.headers.set("Cache-Control", "no-store");
    return response;
  }
  return NextResponse.next();
}

export const config = {matcher: ["/", "/api/:path*"]};
