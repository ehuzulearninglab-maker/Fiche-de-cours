import { NextRequest, NextResponse } from "next/server";
import { extractTextFromPDF } from "@/lib/pdf";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;

    if (!file) {
      return NextResponse.json({ error: "No file provided" }, { status: 400 });
    }

    if (file.type !== "application/pdf") {
      return NextResponse.json({ error: "Only PDF files are accepted" }, { status: 400 });
    }

    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);
    const text = await extractTextFromPDF(buffer);

    if (!text || text.trim().length < 50) {
      return NextResponse.json(
        { error: "Could not extract enough text from the PDF. Please ensure your CV contains readable text." },
        { status: 422 }
      );
    }

    return NextResponse.json({ text: text.substring(0, 8000) });
  } catch {
    return NextResponse.json({ error: "Failed to process PDF" }, { status: 500 });
  }
}
