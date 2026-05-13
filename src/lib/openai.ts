import { GoogleGenerativeAI } from "@google/generative-ai";
import type { PortfolioData } from "./types";

function getClient(): GoogleGenerativeAI {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error("GEMINI_API_KEY environment variable is required");
  }
  return new GoogleGenerativeAI(apiKey);
}

const systemPrompt = `You are a professional CV analyzer and portfolio content creator. 
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
If information is missing, infer reasonable defaults.`;

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const MODELS = ["gemini-2.0-flash", "gemini-1.5-flash"] as const;

export async function analyzeCV(cvText: string): Promise<PortfolioData> {
  const genAI = getClient();
  let lastError: Error | null = null;

  for (const modelName of MODELS) {
    const model = genAI.getGenerativeModel({
      model: modelName,
      systemInstruction: systemPrompt,
    });

    const maxRetries = 3;
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        console.log(`Trying ${modelName} (attempt ${attempt + 1}/${maxRetries})`);
        const result = await model.generateContent(
          `Analyze this CV and generate portfolio content:\n\n${cvText}`
        );

        const content = result.response.text();
        if (!content) {
          throw new Error("No response from Gemini");
        }

        const jsonMatch = content.match(/\{[\s\S]*\}/);
        if (!jsonMatch) {
          throw new Error("Could not parse JSON from response");
        }

        return JSON.parse(jsonMatch[0]) as PortfolioData;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        const is429 = lastError.message.includes("429") || lastError.message.includes("Too Many Requests");
        if (!is429) {
          throw lastError;
        }
        if (attempt < maxRetries - 1) {
          const delay = Math.pow(2, attempt + 1) * 5000;
          console.log(`Rate limit on ${modelName}, retrying in ${delay / 1000}s`);
          await sleep(delay);
        } else {
          console.log(`Rate limit exhausted on ${modelName}, trying next model...`);
        }
      }
    }
  }

  throw lastError ?? new Error("Failed to generate portfolio");
}
