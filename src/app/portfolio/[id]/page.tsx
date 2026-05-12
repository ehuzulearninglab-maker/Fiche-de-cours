import { prisma } from "@/lib/db";
import { notFound } from "next/navigation";
import PortfolioView from "@/components/portfolio/PortfolioView";
import type { PortfolioData } from "@/lib/types";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function PortfolioPage({ params }: PageProps) {
  const { id } = await params;

  const portfolio = await prisma.portfolio.findUnique({ where: { id } });

  if (!portfolio || portfolio.revoked) {
    notFound();
  }

  const data: PortfolioData = {
    fullName: portfolio.fullName,
    title: portfolio.title,
    bio: portfolio.bio,
    skills: JSON.parse(portfolio.skills),
    education: JSON.parse(portfolio.education),
    experience: JSON.parse(portfolio.experience),
    projects: JSON.parse(portfolio.projects),
    languages: JSON.parse(portfolio.languages),
    contact: JSON.parse(portfolio.contact),
    certifications: JSON.parse(portfolio.certifications),
    theme: JSON.parse(portfolio.theme),
  };

  return <PortfolioView data={data} id={id} showControls />;
}
