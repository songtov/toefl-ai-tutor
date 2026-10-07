import { type NextRequest, NextResponse } from "next/server";

const ALLOWED_HOSTNAMES = new Set(["localhost", "127.0.0.1"]);

// Blocks DNS rebinding: another site resolving its name to 127.0.0.1 must not reach the API proxy.
export function proxy(request: NextRequest) {
  const hostname = (request.headers.get("host") ?? "").replace(/:\d+$/, "");
  if (!ALLOWED_HOSTNAMES.has(hostname)) {
    return new NextResponse("Invalid host", { status: 400 });
  }
  return NextResponse.next();
}
