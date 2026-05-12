import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const token = request.headers.get("x-admin-token");

  if (!process.env.ADMIN_TOKEN || token !== process.env.ADMIN_TOKEN) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  const { revoked } = await request.json();

  const portfolio = await prisma.portfolio.update({
    where: { id },
    data: { revoked: Boolean(revoked) },
  });

  return NextResponse.json({ success: true, revoked: portfolio.revoked });
}
