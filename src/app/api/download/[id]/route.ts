import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import type { PortfolioData, Skill, Education, Experience, Project } from "@/lib/types";

function generateHTML(data: PortfolioData): string {
  const theme = data.theme;
  const initials = data.fullName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .substring(0, 2)
    .toUpperCase();

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${data.fullName} — Portfolio</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',system-ui,-apple-system,sans-serif;background:${theme.background};color:${theme.text};line-height:1.6}
.container{max-width:800px;margin:0 auto;padding:0 24px}
.hero{min-height:70vh;display:flex;align-items:center;justify-content:center;text-align:center;position:relative}
.hero::before{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:600px;height:400px;background:radial-gradient(ellipse,${theme.primary}15,transparent 60%);pointer-events:none}
.avatar{width:112px;height:112px;border-radius:50%;background:linear-gradient(135deg,${theme.primary},${theme.accent});display:flex;align-items:center;justify-content:center;font-size:32px;font-weight:700;color:#fff;margin:0 auto 24px;box-shadow:0 0 60px ${theme.primary}30}
h1{font-size:clamp(2rem,5vw,3.5rem);font-weight:700;letter-spacing:-0.02em}
.title-role{font-size:1.25rem;color:${theme.primary};font-weight:300;margin-top:8px}
.contact-links{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:24px}
.contact-links a,.contact-links span{padding:8px 16px;border-radius:8px;font-size:14px;border:1px solid ${theme.primary}30;color:${theme.textSecondary};text-decoration:none;transition:transform 0.2s}
.contact-links a:hover{transform:scale(1.05)}
section{padding:80px 0}
.section-title{font-size:12px;font-weight:500;text-transform:uppercase;letter-spacing:3px;color:${theme.primary};margin-bottom:40px}
.bio{font-size:18px;color:${theme.textSecondary};white-space:pre-line}
.skills-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.skill-card{padding:16px;border-radius:12px;background:${theme.surface};border:1px solid ${theme.primary}10}
.skill-header{display:flex;justify-content:space-between;margin-bottom:8px;font-size:14px}
.skill-cat{color:${theme.textSecondary};font-size:12px}
.skill-bar{height:6px;border-radius:3px;background:${theme.primary}15;overflow:hidden}
.skill-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,${theme.primary},${theme.accent})}
.timeline-item{position:relative;padding-left:32px;border-left:2px solid ${theme.primary}30;margin-bottom:32px}
.timeline-item::before{content:'';position:absolute;left:-5px;top:6px;width:8px;height:8px;border-radius:50%;background:${theme.primary}}
.timeline-item h3{font-size:18px;font-weight:600}
.timeline-meta{font-size:14px;margin-top:4px}
.timeline-meta .company{color:${theme.primary}}
.timeline-meta .period{color:${theme.textSecondary}}
.timeline-desc{font-size:14px;color:${theme.textSecondary};margin-top:8px}
.highlights{list-style:none;margin-top:8px}
.highlights li{font-size:14px;color:${theme.textSecondary};padding:2px 0}
.highlights li::before{content:'▸ ';color:${theme.primary}}
.projects-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:24px}
.project-card{padding:24px;border-radius:16px;background:${theme.surface};border:1px solid ${theme.primary}15;transition:transform 0.2s}
.project-card:hover{transform:scale(1.02)}
.project-icon{width:40px;height:40px;border-radius:8px;background:linear-gradient(135deg,${theme.primary}40,${theme.accent}40);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:700;color:#fff;margin-bottom:16px}
.project-card h3{font-size:18px;font-weight:600;margin-bottom:8px}
.project-card p{font-size:14px;color:${theme.textSecondary};margin-bottom:16px}
.tags{display:flex;flex-wrap:wrap;gap:8px}
.tag{padding:4px 10px;border-radius:99px;font-size:12px;border:1px solid ${theme.primary}30;color:${theme.primary};background:${theme.primary}08}
.edu-card{padding:20px;border-radius:12px;background:${theme.surface};border:1px solid ${theme.primary}10;margin-bottom:16px}
.edu-card h3{font-weight:600}
.edu-meta{font-size:14px;margin-top:4px}
.edu-meta .school{color:${theme.primary}}
.edu-meta .year{color:${theme.textSecondary}}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:48px}
@media(max-width:640px){.two-col{grid-template-columns:1fr}}
.list-item{padding:10px 16px;border-radius:8px;background:${theme.surface};border:1px solid ${theme.primary}10;font-size:14px;margin-bottom:8px}
footer{text-align:center;padding:32px;border-top:1px solid ${theme.primary}10;font-size:12px;color:${theme.textSecondary}}
footer a{color:${theme.primary};text-decoration:none}
</style>
</head>
<body>

<section class="hero">
<div class="container" style="position:relative;z-index:1">
<div class="avatar">${initials}</div>
<h1>${data.fullName}</h1>
<p class="title-role">${data.title}</p>
<div class="contact-links">
${data.contact.email ? `<a href="mailto:${data.contact.email}">${data.contact.email}</a>` : ""}
${data.contact.location ? `<span>${data.contact.location}</span>` : ""}
${data.contact.linkedin ? `<a href="${data.contact.linkedin}" target="_blank">LinkedIn</a>` : ""}
${data.contact.github ? `<a href="${data.contact.github}" target="_blank">GitHub</a>` : ""}
</div>
</div>
</section>

<section>
<div class="container">
<h2 class="section-title">About</h2>
<div class="bio">${data.bio}</div>
</div>
</section>

${data.skills.length > 0 ? `
<section>
<div class="container">
<h2 class="section-title">Skills</h2>
<div class="skills-grid">
${data.skills.map((s: Skill) => `
<div class="skill-card">
<div class="skill-header"><span>${s.name}</span><span class="skill-cat">${s.category}</span></div>
<div class="skill-bar"><div class="skill-fill" style="width:${s.level}%"></div></div>
</div>`).join("")}
</div>
</div>
</section>` : ""}

${data.experience.length > 0 ? `
<section>
<div class="container">
<h2 class="section-title">Experience</h2>
${data.experience.map((e: Experience) => `
<div class="timeline-item">
<h3>${e.role}</h3>
<div class="timeline-meta"><span class="company">${e.company}</span> • <span class="period">${e.period}</span></div>
<p class="timeline-desc">${e.description}</p>
${e.highlights?.length ? `<ul class="highlights">${e.highlights.map((h: string) => `<li>${h}</li>`).join("")}</ul>` : ""}
</div>`).join("")}
</div>
</section>` : ""}

${data.projects.length > 0 ? `
<section>
<div class="container">
<h2 class="section-title">Projects</h2>
<div class="projects-grid">
${data.projects.map((p: Project) => `
<div class="project-card">
<div class="project-icon">${p.name[0]}</div>
<h3>${p.name}</h3>
<p>${p.description}</p>
<div class="tags">${p.technologies.map((t: string) => `<span class="tag">${t}</span>`).join("")}</div>
${p.link ? `<a href="${p.link}" target="_blank" style="display:inline-block;margin-top:16px;font-size:14px;color:${theme.primary}">View Project →</a>` : ""}
</div>`).join("")}
</div>
</div>
</section>` : ""}

${data.education.length > 0 ? `
<section>
<div class="container">
<h2 class="section-title">Education</h2>
${data.education.map((e: Education) => `
<div class="edu-card">
<h3>${e.degree}</h3>
<div class="edu-meta"><span class="school">${e.school}</span> • <span class="year">${e.year}</span></div>
${e.description ? `<p style="font-size:14px;color:${theme.textSecondary};margin-top:8px">${e.description}</p>` : ""}
</div>`).join("")}
</div>
</section>` : ""}

${data.languages.length > 0 || data.certifications.length > 0 ? `
<section>
<div class="container">
<div class="two-col">
${data.languages.length > 0 ? `<div><h2 class="section-title">Languages</h2>${data.languages.map((l: string) => `<div class="list-item">${l}</div>`).join("")}</div>` : ""}
${data.certifications.length > 0 ? `<div><h2 class="section-title">Certifications</h2>${data.certifications.map((c: string) => `<div class="list-item">${c}</div>`).join("")}</div>` : ""}
</div>
</div>
</section>` : ""}

<footer>Generated by <a href="#">CV2Portfolio AI</a></footer>
</body>
</html>`;
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const portfolio = await prisma.portfolio.findUnique({ where: { id } });

    if (!portfolio || portfolio.revoked) {
      return NextResponse.json({ error: "Portfolio not found" }, { status: 404 });
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

    const html = generateHTML(data);

    return new NextResponse(html, {
      headers: {
        "Content-Type": "text/html",
        "Content-Disposition": `attachment; filename="${data.fullName.replace(/\s+/g, "_")}_portfolio.html"`,
      },
    });
  } catch {
    return NextResponse.json({ error: "Download failed" }, { status: 500 });
  }
}
