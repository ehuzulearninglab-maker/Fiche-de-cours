import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(request: NextRequest) {
  const token = request.headers.get("x-admin-token");

  if (!process.env.ADMIN_TOKEN || token !== process.env.ADMIN_TOKEN) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const portfolios = await prisma.portfolio.findMany({
    orderBy: { createdAt: "desc" },
    select: {
      id: true,
      fullName: true,
      title: true,
      revoked: true,
      createdAt: true,
    },
  });

  return NextResponse.json({ portfolios });
}
