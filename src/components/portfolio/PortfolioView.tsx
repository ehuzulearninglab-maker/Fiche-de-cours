"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useState } from "react";
import type { PortfolioData } from "@/lib/types";

const fadeUp = {
  hidden: { opacity: 0, y: 30 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] },
  }),
};

interface PortfolioViewProps {
  data: PortfolioData;
  id: string;
  showControls?: boolean;
}

export default function PortfolioView({ data, id, showControls }: PortfolioViewProps) {
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const theme = data.theme;

  const shareUrl = typeof window !== "undefined"
    ? `${window.location.origin}/p/${id}`
    : `/p/${id}`;

  const handleCopyLink = () => {
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const res = await fetch(`/api/download/${id}`);
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${data.fullName.replace(/\s+/g, "_")}_portfolio.html`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      alert("Download failed. Please try again.");
    }
    setDownloading(false);
  };

  return (
    <div
      className="min-h-screen"
      style={{
        background: theme.background,
        color: theme.text,
        fontFamily: "Inter, system-ui, -apple-system, sans-serif",
      }}
    >
      {/* Controls Bar */}
      {showControls && (
        <motion.div
          initial={{ y: -20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="fixed top-0 left-0 right-0 z-50 border-b"
          style={{
            background: `${theme.surface}ee`,
            backdropFilter: "blur(20px)",
            borderColor: `${theme.primary}20`,
          }}
        >
          <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
            <Link
              href="/"
              className="text-sm flex items-center gap-2 opacity-70 hover:opacity-100 transition-opacity"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              CV2Portfolio AI
            </Link>
            <div className="flex items-center gap-3">
              <button
                onClick={handleCopyLink}
                className="px-4 py-1.5 rounded-lg text-sm font-medium border transition-all"
                style={{
                  borderColor: `${theme.primary}40`,
                  color: theme.primary,
                }}
              >
                {copied ? "Copied!" : "Share Link"}
              </button>
              <button
                onClick={handleDownload}
                disabled={downloading}
                className="px-4 py-1.5 rounded-lg text-sm font-medium text-white transition-all"
                style={{ background: theme.primary }}
              >
                {downloading ? "..." : "Download"}
              </button>
            </div>
          </div>
        </motion.div>
      )}

      {/* Hero Section */}
      <section
        className="relative min-h-[70vh] flex items-center justify-center"
        style={{ paddingTop: showControls ? "3.5rem" : 0 }}
      >
        <div
          className="absolute inset-0"
          style={{
            background: `radial-gradient(ellipse at 50% 0%, ${theme.primary}15, transparent 60%)`,
          }}
        />
        <div className="relative z-10 text-center px-6 py-20 max-w-4xl mx-auto">
          <motion.div initial="hidden" animate="visible" className="space-y-6">
            {/* Avatar */}
            <motion.div custom={0} variants={fadeUp} className="flex justify-center">
              <div
                className="w-28 h-28 rounded-full flex items-center justify-center text-4xl font-bold text-white"
                style={{
                  background: `linear-gradient(135deg, ${theme.primary}, ${theme.accent})`,
                  boxShadow: `0 0 60px ${theme.primary}30`,
                }}
              >
                {data.fullName
                  .split(" ")
                  .map((n) => n[0])
                  .join("")
                  .substring(0, 2)
                  .toUpperCase()}
              </div>
            </motion.div>

            <motion.h1
              custom={1}
              variants={fadeUp}
              className="text-4xl sm:text-6xl lg:text-7xl font-bold tracking-tight"
            >
              {data.fullName}
            </motion.h1>

            <motion.p
              custom={2}
              variants={fadeUp}
              className="text-xl sm:text-2xl font-light"
              style={{ color: theme.primary }}
            >
              {data.title}
            </motion.p>

            <motion.div custom={3} variants={fadeUp} className="flex flex-wrap justify-center gap-3">
              {data.contact.email && (
                <a
                  href={`mailto:${data.contact.email}`}
                  className="px-4 py-2 rounded-lg text-sm border transition-all hover:scale-105"
                  style={{ borderColor: `${theme.primary}30`, color: theme.textSecondary }}
                >
                  {data.contact.email}
                </a>
              )}
              {data.contact.location && (
                <span
                  className="px-4 py-2 rounded-lg text-sm border"
                  style={{ borderColor: `${theme.primary}20`, color: theme.textSecondary }}
                >
                  {data.contact.location}
                </span>
              )}
              {data.contact.linkedin && (
                <a
                  href={data.contact.linkedin}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-4 py-2 rounded-lg text-sm border transition-all hover:scale-105"
                  style={{ borderColor: `${theme.primary}30`, color: theme.textSecondary }}
                >
                  LinkedIn
                </a>
              )}
              {data.contact.github && (
                <a
                  href={data.contact.github}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-4 py-2 rounded-lg text-sm border transition-all hover:scale-105"
                  style={{ borderColor: `${theme.primary}30`, color: theme.textSecondary }}
                >
                  GitHub
                </a>
              )}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* About Section */}
      <section className="py-20 px-6">
        <div className="max-w-3xl mx-auto">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
          >
            <motion.h2
              custom={0}
              variants={fadeUp}
              className="text-sm font-medium uppercase tracking-widest mb-6"
              style={{ color: theme.primary }}
            >
              About
            </motion.h2>
            <motion.div
              custom={1}
              variants={fadeUp}
              className="text-lg leading-relaxed whitespace-pre-line"
              style={{ color: theme.textSecondary }}
            >
              {data.bio}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* Skills Section */}
      {data.skills.length > 0 && (
        <section className="py-20 px-6">
          <div className="max-w-4xl mx-auto">
            <motion.div
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-80px" }}
            >
              <motion.h2
                custom={0}
                variants={fadeUp}
                className="text-sm font-medium uppercase tracking-widest mb-10"
                style={{ color: theme.primary }}
              >
                Skills
              </motion.h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {data.skills.map((skill, i) => (
                  <motion.div
                    key={skill.name}
                    custom={i + 1}
                    variants={fadeUp}
                    className="p-4 rounded-xl border"
                    style={{
                      background: `${theme.surface}`,
                      borderColor: `${theme.primary}10`,
                    }}
                  >
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-medium text-sm">{skill.name}</span>
                      <span className="text-xs" style={{ color: theme.textSecondary }}>
                        {skill.category}
                      </span>
                    </div>
                    <div
                      className="h-1.5 rounded-full overflow-hidden"
                      style={{ background: `${theme.primary}15` }}
                    >
                      <motion.div
                        className="h-full rounded-full"
                        style={{
                          background: `linear-gradient(90deg, ${theme.primary}, ${theme.accent})`,
                        }}
                        initial={{ width: 0 }}
                        whileInView={{ width: `${skill.level}%` }}
                        viewport={{ once: true }}
                        transition={{ duration: 1, delay: i * 0.05 }}
                      />
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>
        </section>
      )}

      {/* Experience Timeline */}
      {data.experience.length > 0 && (
        <section className="py-20 px-6">
          <div className="max-w-3xl mx-auto">
            <motion.div
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-80px" }}
            >
              <motion.h2
                custom={0}
                variants={fadeUp}
                className="text-sm font-medium uppercase tracking-widest mb-10"
                style={{ color: theme.primary }}
              >
                Experience
              </motion.h2>
              <div className="space-y-8">
                {data.experience.map((exp, i) => (
                  <motion.div
                    key={`${exp.company}-${exp.role}`}
                    custom={i + 1}
                    variants={fadeUp}
                    className="relative pl-8 border-l-2"
                    style={{ borderColor: `${theme.primary}30` }}
                  >
                    <div
                      className="absolute left-[-5px] top-1 w-2 h-2 rounded-full"
                      style={{ background: theme.primary }}
                    />
                    <div className="space-y-2">
                      <h3 className="text-lg font-semibold">{exp.role}</h3>
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span style={{ color: theme.primary }}>{exp.company}</span>
                        <span style={{ color: theme.textSecondary }}>•</span>
                        <span style={{ color: theme.textSecondary }}>{exp.period}</span>
                      </div>
                      <p className="text-sm leading-relaxed" style={{ color: theme.textSecondary }}>
                        {exp.description}
                      </p>
                      {exp.highlights && exp.highlights.length > 0 && (
                        <ul className="space-y-1 mt-2">
                          {exp.highlights.map((h, j) => (
                            <li key={j} className="text-sm flex items-start gap-2" style={{ color: theme.textSecondary }}>
                              <span style={{ color: theme.primary }} className="mt-1.5">▸</span>
                              {h}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>
        </section>
      )}

      {/* Projects Gallery */}
      {data.projects.length > 0 && (
        <section className="py-20 px-6">
          <div className="max-w-5xl mx-auto">
            <motion.div
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-80px" }}
            >
              <motion.h2
                custom={0}
                variants={fadeUp}
                className="text-sm font-medium uppercase tracking-widest mb-10"
                style={{ color: theme.primary }}
              >
                Projects
              </motion.h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {data.projects.map((project, i) => (
                  <motion.div
                    key={project.name}
                    custom={i + 1}
                    variants={fadeUp}
                    className="group p-6 rounded-2xl border transition-all hover:scale-[1.02]"
                    style={{
                      background: theme.surface,
                      borderColor: `${theme.primary}15`,
                    }}
                  >
                    <div
                      className="w-10 h-10 rounded-lg mb-4 flex items-center justify-center text-white text-lg font-bold"
                      style={{
                        background: `linear-gradient(135deg, ${theme.primary}40, ${theme.accent}40)`,
                      }}
                    >
                      {project.name[0]}
                    </div>
                    <h3 className="text-lg font-semibold mb-2">{project.name}</h3>
                    <p className="text-sm leading-relaxed mb-4" style={{ color: theme.textSecondary }}>
                      {project.description}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {project.technologies.map((tech) => (
                        <span
                          key={tech}
                          className="px-2.5 py-0.5 rounded-full text-xs border"
                          style={{
                            color: theme.primary,
                            borderColor: `${theme.primary}30`,
                            background: `${theme.primary}08`,
                          }}
                        >
                          {tech}
                        </span>
                      ))}
                    </div>
                    {project.link && (
                      <a
                        href={project.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-block mt-4 text-sm hover:underline"
                        style={{ color: theme.primary }}
                      >
                        View Project →
                      </a>
                    )}
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>
        </section>
      )}

      {/* Education */}
      {data.education.length > 0 && (
        <section className="py-20 px-6">
          <div className="max-w-3xl mx-auto">
            <motion.div
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-80px" }}
            >
              <motion.h2
                custom={0}
                variants={fadeUp}
                className="text-sm font-medium uppercase tracking-widest mb-10"
                style={{ color: theme.primary }}
              >
                Education
              </motion.h2>
              <div className="space-y-6">
                {data.education.map((edu, i) => (
                  <motion.div
                    key={`${edu.school}-${edu.degree}`}
                    custom={i + 1}
                    variants={fadeUp}
                    className="p-5 rounded-xl border"
                    style={{
                      background: theme.surface,
                      borderColor: `${theme.primary}10`,
                    }}
                  >
                    <h3 className="font-semibold">{edu.degree}</h3>
                    <div className="flex items-center gap-2 text-sm mt-1">
                      <span style={{ color: theme.primary }}>{edu.school}</span>
                      <span style={{ color: theme.textSecondary }}>• {edu.year}</span>
                    </div>
                    {edu.description && (
                      <p className="text-sm mt-2" style={{ color: theme.textSecondary }}>
                        {edu.description}
                      </p>
                    )}
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>
        </section>
      )}

      {/* Languages & Certifications */}
      {(data.languages.length > 0 || data.certifications.length > 0) && (
        <section className="py-20 px-6">
          <div className="max-w-3xl mx-auto grid grid-cols-1 sm:grid-cols-2 gap-12">
            {data.languages.length > 0 && (
              <motion.div
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true }}
              >
                <motion.h2
                  custom={0}
                  variants={fadeUp}
                  className="text-sm font-medium uppercase tracking-widest mb-6"
                  style={{ color: theme.primary }}
                >
                  Languages
                </motion.h2>
                <div className="space-y-2">
                  {data.languages.map((lang, i) => (
                    <motion.div
                      key={lang}
                      custom={i + 1}
                      variants={fadeUp}
                      className="px-4 py-2.5 rounded-lg border text-sm"
                      style={{
                        background: theme.surface,
                        borderColor: `${theme.primary}10`,
                      }}
                    >
                      {lang}
                    </motion.div>
                  ))}
                </div>
              </motion.div>
            )}

            {data.certifications.length > 0 && (
              <motion.div
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true }}
              >
                <motion.h2
                  custom={0}
                  variants={fadeUp}
                  className="text-sm font-medium uppercase tracking-widest mb-6"
                  style={{ color: theme.primary }}
                >
                  Certifications
                </motion.h2>
                <div className="space-y-2">
                  {data.certifications.map((cert, i) => (
                    <motion.div
                      key={cert}
                      custom={i + 1}
                      variants={fadeUp}
                      className="px-4 py-2.5 rounded-lg border text-sm"
                      style={{
                        background: theme.surface,
                        borderColor: `${theme.primary}10`,
                      }}
                    >
                      {cert}
                    </motion.div>
                  ))}
                </div>
              </motion.div>
            )}
          </div>
        </section>
      )}

      {/* Footer */}
      <footer
        className="py-8 text-center border-t text-xs"
        style={{
          borderColor: `${theme.primary}10`,
          color: theme.textSecondary,
        }}
      >
        <p>
          Generated by{" "}
          <Link href="/" className="hover:underline" style={{ color: theme.primary }}>
            CV2Portfolio AI
          </Link>
        </p>
      </footer>
    </div>
  );
}
