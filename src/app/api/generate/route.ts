import { NextRequest, NextResponse } from "next/server";
import { analyzeCV } from "@/lib/openai";
import { prisma } from "@/lib/db";

export async function POST(request: NextRequest) {
  try {
    const { cvText } = await request.json();

    if (!cvText || typeof cvText !== "string") {
      return NextResponse.json({ error: "CV text is required" }, { status: 400 });
    }

    if (!process.env.GEMINI_API_KEY) {
      return NextResponse.json({ error: "Gemini API key not configured" }, { status: 500 });
    }

    const portfolioData = await analyzeCV(cvText);

    const portfolio = await prisma.portfolio.create({
      data: {
        fullName: portfolioData.fullName,
        title: portfolioData.title,
        bio: portfolioData.bio,
        skills: JSON.stringify(portfolioData.skills),
        education: JSON.stringify(portfolioData.education),
        experience: JSON.stringify(portfolioData.experience),
        projects: JSON.stringify(portfolioData.projects),
        languages: JSON.stringify(portfolioData.languages),
        contact: JSON.stringify(portfolioData.contact),
        certifications: JSON.stringify(portfolioData.certifications),
        theme: JSON.stringify(portfolioData.theme),
      },
    });

    return NextResponse.json({ id: portfolio.id });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to generate portfolio";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
