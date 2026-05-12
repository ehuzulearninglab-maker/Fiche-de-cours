"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useState } from "react";

const fadeUp = {
  hidden: { opacity: 0, y: 40 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.1, duration: 0.6, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] },
  }),
};

const features = [
  {
    icon: "⚡",
    title: "Instant Generation",
    description: "Upload your CV and get a premium portfolio in under 30 seconds.",
  },
  {
    icon: "🤖",
    title: "AI-Powered",
    description: "Advanced AI rewrites your bio, enhances descriptions, and creates compelling content.",
  },
  {
    icon: "🎨",
    title: "Premium Design",
    description: "Auto-generated modern themes with glassmorphism, gradients, and smooth animations.",
  },
  {
    icon: "📱",
    title: "Fully Responsive",
    description: "Your portfolio looks perfect on desktop, tablet, and mobile devices.",
  },
  {
    icon: "🔗",
    title: "Shareable Link",
    description: "Get a unique public URL to share your portfolio with anyone, anywhere.",
  },
  {
    icon: "📥",
    title: "Download & Own",
    description: "Download your complete portfolio as a standalone HTML file.",
  },
];

const steps = [
  { number: "01", title: "Upload Your CV", description: "Drag & drop your PDF resume" },
  { number: "02", title: "AI Analyzes", description: "Our AI extracts and enhances your content" },
  { number: "03", title: "Portfolio Generated", description: "Get a stunning portfolio in seconds" },
  { number: "04", title: "Share & Download", description: "Share your link or download your site" },
];

export default function LandingPage() {
  const [hoveredFeature, setHoveredFeature] = useState<number | null>(null);

  return (
    <div className="relative overflow-hidden">
      {/* Background Effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-gradient-to-b from-primary/10 via-secondary/5 to-transparent rounded-full blur-3xl pointer-events-none" />
      <div className="fixed bottom-0 right-0 w-[600px] h-[400px] bg-gradient-to-tl from-accent/8 via-transparent to-transparent rounded-full blur-3xl pointer-events-none" />

      {/* Navbar */}
      <motion.nav
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6 }}
        className="fixed top-0 left-0 right-0 z-50 glass-strong"
      >
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center text-white font-bold text-sm">
              CV
            </div>
            <span className="font-semibold text-lg">CV2Portfolio</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
              AI
            </span>
          </div>
          <Link
            href="/upload"
            className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary/90 transition-all hover:shadow-lg hover:shadow-primary/25"
          >
            Get Started
          </Link>
        </div>
      </motion.nav>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center pt-16">
        <div className="max-w-5xl mx-auto px-6 text-center">
          <motion.div
            initial="hidden"
            animate="visible"
            className="space-y-8"
          >
            <motion.div custom={0} variants={fadeUp} className="inline-block">
              <span className="px-4 py-1.5 rounded-full text-sm font-medium bg-primary/10 text-primary border border-primary/20">
                Powered by AI
              </span>
            </motion.div>

            <motion.h1
              custom={1}
              variants={fadeUp}
              className="text-5xl sm:text-7xl lg:text-8xl font-bold tracking-tight leading-[0.9]"
            >
              Transform your CV
              <br />
              <span className="text-gradient">into a portfolio</span>
            </motion.h1>

            <motion.p
              custom={2}
              variants={fadeUp}
              className="text-lg sm:text-xl text-text-secondary max-w-2xl mx-auto leading-relaxed"
            >
              Upload your resume PDF. Our AI instantly creates a beautiful,
              professional portfolio website. No design skills needed.
            </motion.p>

            <motion.div custom={3} variants={fadeUp} className="flex flex-col sm:flex-row gap-4 justify-center">
              <Link
                href="/upload"
                className="group relative px-8 py-4 rounded-xl bg-gradient-to-r from-primary to-secondary text-white font-semibold text-lg overflow-hidden transition-all hover:shadow-2xl hover:shadow-primary/25 hover:scale-[1.02]"
              >
                <span className="relative z-10">Upload Your CV</span>
                <div className="absolute inset-0 bg-gradient-to-r from-secondary to-accent opacity-0 group-hover:opacity-100 transition-opacity" />
              </Link>
              <a
                href="#features"
                className="px-8 py-4 rounded-xl border border-border text-text-secondary font-medium text-lg hover:border-primary/50 hover:text-foreground transition-all"
              >
                Learn More
              </a>
            </motion.div>

            {/* Hero Visual */}
            <motion.div
              custom={4}
              variants={fadeUp}
              className="relative mt-16 mx-auto max-w-3xl"
            >
              <div className="relative glass rounded-2xl p-1 glow-primary">
                <div className="rounded-xl overflow-hidden bg-surface">
                  <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
                    <div className="w-3 h-3 rounded-full bg-red-500/80" />
                    <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
                    <div className="w-3 h-3 rounded-full bg-green-500/80" />
                    <span className="ml-3 text-xs text-text-secondary font-mono">cv2portfolio.ai</span>
                  </div>
                  <div className="p-8 space-y-6">
                    <div className="flex items-center gap-4">
                      <div className="w-16 h-16 rounded-full bg-gradient-to-br from-primary to-accent" />
                      <div className="space-y-2">
                        <div className="h-4 w-40 rounded bg-surface-light" />
                        <div className="h-3 w-28 rounded bg-surface-light" />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="h-3 w-full rounded bg-surface-light" />
                      <div className="h-3 w-4/5 rounded bg-surface-light" />
                      <div className="h-3 w-3/5 rounded bg-surface-light" />
                    </div>
                    <div className="flex gap-2">
                      {["React", "TypeScript", "Node.js", "AI/ML"].map((tag) => (
                        <span key={tag} className="px-3 py-1 rounded-full text-xs bg-primary/10 text-primary border border-primary/20">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              <div className="absolute -top-4 -right-4 w-24 h-24 bg-accent/20 rounded-full blur-2xl animate-pulse-glow" />
              <div className="absolute -bottom-4 -left-4 w-32 h-32 bg-primary/20 rounded-full blur-2xl animate-pulse-glow" />
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* How It Works */}
      <section className="relative py-32">
        <div className="max-w-5xl mx-auto px-6">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-100px" }}
            className="text-center mb-16"
          >
            <motion.p custom={0} variants={fadeUp} className="text-primary text-sm font-medium mb-3">
              HOW IT WORKS
            </motion.p>
            <motion.h2 custom={1} variants={fadeUp} className="text-4xl sm:text-5xl font-bold">
              Four simple steps
            </motion.h2>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {steps.map((step, i) => (
              <motion.div
                key={step.number}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true }}
                custom={i}
                variants={fadeUp}
                className="relative p-6 rounded-2xl glass group hover:border-primary/30 transition-all"
              >
                <span className="text-5xl font-bold text-gradient opacity-20 group-hover:opacity-40 transition-opacity">
                  {step.number}
                </span>
                <h3 className="text-lg font-semibold mt-2">{step.title}</h3>
                <p className="text-text-secondary text-sm mt-1">{step.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="relative py-32">
        <div className="max-w-6xl mx-auto px-6">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-100px" }}
            className="text-center mb-16"
          >
            <motion.p custom={0} variants={fadeUp} className="text-primary text-sm font-medium mb-3">
              FEATURES
            </motion.p>
            <motion.h2 custom={1} variants={fadeUp} className="text-4xl sm:text-5xl font-bold">
              Everything you need
            </motion.h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature, i) => (
              <motion.div
                key={feature.title}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true }}
                custom={i}
                variants={fadeUp}
                onMouseEnter={() => setHoveredFeature(i)}
                onMouseLeave={() => setHoveredFeature(null)}
                className="relative p-6 rounded-2xl glass group hover:border-primary/30 transition-all cursor-default"
              >
                <div className={`absolute inset-0 rounded-2xl bg-gradient-to-br from-primary/5 to-accent/5 opacity-0 transition-opacity ${hoveredFeature === i ? "opacity-100" : ""}`} />
                <div className="relative">
                  <span className="text-3xl mb-4 block">{feature.icon}</span>
                  <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
                  <p className="text-text-secondary text-sm leading-relaxed">{feature.description}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials Mock */}
      <section className="relative py-32">
        <div className="max-w-5xl mx-auto px-6">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-100px" }}
            className="text-center mb-16"
          >
            <motion.p custom={0} variants={fadeUp} className="text-primary text-sm font-medium mb-3">
              TESTIMONIALS
            </motion.p>
            <motion.h2 custom={1} variants={fadeUp} className="text-4xl sm:text-5xl font-bold">
              Loved by professionals
            </motion.h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { name: "Marie L.", role: "UX Designer", quote: "I couldn't believe my portfolio was generated in seconds. It looks like I hired a professional designer!" },
              { name: "Ahmed K.", role: "Software Engineer", quote: "The AI understood my experience perfectly and created an incredible portfolio. The WOW effect is real." },
              { name: "Claire D.", role: "Marketing Manager", quote: "I shared my portfolio link during a job interview. The recruiter was impressed by the design quality." },
            ].map((testimonial, i) => (
              <motion.div
                key={testimonial.name}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true }}
                custom={i}
                variants={fadeUp}
                className="p-6 rounded-2xl glass"
              >
                <div className="flex items-center gap-1 mb-4">
                  {[...Array(5)].map((_, j) => (
                    <svg key={j} className="w-4 h-4 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                    </svg>
                  ))}
                </div>
                <p className="text-sm text-text-secondary leading-relaxed mb-4">&ldquo;{testimonial.quote}&rdquo;</p>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-accent" />
                  <div>
                    <p className="text-sm font-semibold">{testimonial.name}</p>
                    <p className="text-xs text-text-secondary">{testimonial.role}</p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative py-32">
        <div className="max-w-3xl mx-auto px-6 text-center">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-100px" }}
            className="space-y-8"
          >
            <motion.h2 custom={0} variants={fadeUp} className="text-4xl sm:text-6xl font-bold">
              Ready to transform
              <br />
              <span className="text-gradient">your career?</span>
            </motion.h2>
            <motion.p custom={1} variants={fadeUp} className="text-lg text-text-secondary">
              Join thousands of professionals who already created their premium portfolio.
            </motion.p>
            <motion.div custom={2} variants={fadeUp}>
              <Link
                href="/upload"
                className="inline-block px-10 py-5 rounded-xl bg-gradient-to-r from-primary to-secondary text-white font-semibold text-lg hover:shadow-2xl hover:shadow-primary/25 hover:scale-[1.02] transition-all"
              >
                Create My Portfolio Now
              </Link>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-8">
        <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-primary to-accent flex items-center justify-center text-white font-bold text-[10px]">
              CV
            </div>
            <span className="text-sm text-text-secondary">CV2Portfolio AI</span>
          </div>
          <p className="text-xs text-text-secondary">
            Created by Michel Affedjou — Ehuzu Learning Lab
          </p>
        </div>
      </footer>
    </div>
  );
}
