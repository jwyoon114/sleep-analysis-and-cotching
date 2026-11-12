import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import {demoBlockedResponse, isDemoOnly} from "@/lib/demo-mode";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;
const COOKIE = "sleep_session";
const LIMIT = 4 * 1024 * 1024 + 64 * 1024;
const allowed = /^(?:health|alarms(?:\/test)?|auth\/(?:register|login|logout|me)|analyze|coach|watch\/(?:health\/connection|import|sessions(?:\/[a-zA-Z0-9_-]+(?:\/coaching(?:\/[a-zA-Z0-9_-]+)?)?)?|trash(?:\/(?:session|coaching)\/[a-zA-Z0-9_-]+(?:\/restore)?)?|comparison|backup-policy))$/;

async function handler(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  if (isDemoOnly()) return demoBlockedResponse();
  const { path } = await context.params;
  const endpoint = path.join("/");
  const fail = (detail: string, status: number) => NextResponse.json({detail}, {status, headers: {"Cache-Control": "no-store"}});
  if (!allowed.test(endpoint)) return fail("지원하지 않는 요청입니다.", 404);
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("origin");
    let sameOrigin = false;
    try { sameOrigin = !!origin && new URL(origin).host === request.headers.get("host"); } catch { /* Reject malformed origins. */ }
    if (!sameOrigin) return fail("이 화면에서 다시 요청해 주세요.", 403);
  }
  const jar = await cookies();
  const publicEndpoint = ["health", "auth/login", "auth/register"].includes(endpoint);
  const token = jar.get(COOKIE)?.value;
  if (!publicEndpoint && !token) return fail("로그인이 필요합니다.", 401);
  if (Number(request.headers.get("content-length") || 0) > LIMIT) return fail("파일은 4MiB 이하여야 합니다.", 413);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), endpoint === "coach" ? 55000 : 20000);
  try {
    const base = new URL(process.env.SLEEP_API_URL || "http://127.0.0.1:8011");
    if (!["http:", "https:"].includes(base.protocol)) throw new Error("Invalid backend URL");
    const url = new URL(`${base.pathname.replace(/\/$/, "")}/${endpoint}`, base.origin);
    url.search = request.nextUrl.search;
    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("Content-Type", contentType);
    if (!publicEndpoint && token) headers.set("Authorization", `Bearer ${token}`);
    const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
    if (body && body.byteLength > LIMIT) return fail("파일은 4MiB 이하여야 합니다.", 413);
    const upstream = await fetch(url, {method: request.method, headers, body, cache: "no-store", signal: controller.signal, redirect: "error"});
    const result = await upstream.json();
    if (endpoint === "auth/login" && upstream.ok) {
      if (typeof result.token !== "string") return fail("로그인 응답을 확인할 수 없습니다.", 502);
      jar.set(COOKIE, result.token, {httpOnly: true, secure: request.nextUrl.protocol === "https:" || process.env.VERCEL === "1", sameSite: "strict", path: "/", maxAge: 86400});
      delete result.token;
    }
    if (upstream.status === 401 && !publicEndpoint || endpoint === "auth/logout" && upstream.ok || endpoint === "auth/me" && ["PATCH", "DELETE"].includes(request.method) && upstream.ok) jar.delete(COOKIE);
    return NextResponse.json(result, {status: upstream.status, headers: {"Cache-Control": "no-store, private"}});
  } catch {
    return fail(controller.signal.aborted ? "응답이 지연되고 있습니다. 기록이 저장됐는지 확인한 뒤 다시 시도해 주세요." : "수면 분석 서버에 연결하지 못했습니다. 실행 도구로 서버를 켠 뒤 다시 시도해 주세요.", 502);
  } finally { clearTimeout(timer); }
}

export { handler as GET, handler as POST, handler as PATCH, handler as DELETE };
