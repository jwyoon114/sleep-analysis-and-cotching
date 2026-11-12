import {NextResponse} from "next/server";
import {isDemoOnly} from "@/lib/demo-mode";

export const dynamic = "force-dynamic";
export async function GET() {
  const headers = {"Cache-Control":"no-store"};
  if (isDemoOnly()) return NextResponse.json({status:"demo_only"},{status:503,headers});
  try {
    const upstream = await fetch(`${process.env.SLEEP_API_URL || "http://127.0.0.1:8011"}/ready`,
      {cache:"no-store",redirect:"error",signal:AbortSignal.timeout(15000)});
    return NextResponse.json({status:upstream.ok?"ready":"not_ready"},{status:upstream.ok?200:503,headers});
  } catch {
    return NextResponse.json({status:"not_ready"},{status:503,headers});
  }
}
