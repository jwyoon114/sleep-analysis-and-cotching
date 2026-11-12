import {NextResponse} from "next/server";
import {isDemoOnly} from "@/lib/demo-mode";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(isDemoOnly()
    ? {status:"ok", mode:"demo", data_collection:false}
    : {status:"not_found"}, {
    status:isDemoOnly() ? 200 : 404,
    headers:{"Cache-Control":"no-store"},
  });
}
