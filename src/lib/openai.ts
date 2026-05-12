import OpenAI from "openai";
import type { PortfolioData } from "./types";

function getClient(): OpenAI {
  return new OpenAI({
    apiKey: process.env.OPENAI_API_KEY,
  });
}

export async function analyzeCV(cvText: string): Promise<PortfolioData> {
  const openai = getClient();

  const response = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [
      {
        role: "system",
        content: `You are a professional CV analyzer and portfolio content creator. 
Extract information from the CV text and generate a premium portfolio structure.
Improve the biography to sound professional and engaging.
Enhance project descriptions to be attractive.
Generate elegant summaries.

Return ONLY valid JSON with this exact structure:
{
  "fullName": "string",
  "title": "Professional title",
  "bio": "A professionally rewritten biography (2-3 paragraphs)",
  "skills": [{"name": "string", "level": 85, "category": "Category Name"}],
  "education": [{"degree": "string", "school": "string", "year": "string", "description": "string"}],
  "experience": [{"role": "string", "company": "string", "period": "string", "description": "string", "highlights": ["string"]}],
  "projects": [{"name": "string", "description": "Enhanced description", "technologies": ["string"], "link": "optional url"}],
  "languages": ["Language (Level)"],
  "contact": {"email": "string", "phone": "string", "location": "string", "linkedin": "optional", "github": "optional", "website": "optional"},
  "certifications": ["string"],
  "theme": {
    "primary": "#hex",
    "secondary": "#hex", 
    "accent": "#hex",
    "background": "#0a0a0f",
    "surface": "#141420",
    "text": "#ffffff",
    "textSecondary": "#a0a0b0"
  }
}

For skills level, estimate a number between 60-95.
For theme colors, generate a modern, elegant dark theme with a distinctive accent color based on the person's field.
Make sure the bio is compelling and the content is well-structured.
If information is missing, infer reasonable defaults.`,
      },
      {
        role: "user",
        content: `Analyze this CV and generate portfolio content:\n\n${cvText}`,
      },
    ],
    temperature: 0.7,
    max_tokens: 4000,
  });

  const content = response.choices[0]?.message?.content;
  if (!content) {
    throw new Error("No response from OpenAI");
  }

  const jsonMatch = content.match(/\{[\s\S]*\}/);
  if (!jsonMatch) {
    throw new Error("Could not parse JSON from response");
  }

  return JSON.parse(jsonMatch[0]) as PortfolioData;
}
