"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import { useState, useCallback } from "react";

type UploadState = "idle" | "dragging" | "uploading" | "processing" | "error";

export default function UploadPage() {
  const router = useRouter();
  const [state, setState] = useState<UploadState>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [fileName, setFileName] = useState("");

  const handleFile = useCallback(async (file: File) => {
    if (file.type !== "application/pdf") {
      setError("Please upload a PDF file");
      setState("error");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setError("File size must be under 10MB");
      setState("error");
      return;
    }

    setFileName(file.name);
    setState("uploading");
    setProgress(0);

    const progressInterval = setInterval(() => {
      setProgress((p) => Math.min(p + 2, 30));
    }, 100);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const uploadRes = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });

      if (!uploadRes.ok) {
        const data = await uploadRes.json();
        throw new Error(data.error || "Upload failed");
      }

      const { text } = await uploadRes.json();
      clearInterval(progressInterval);
      setProgress(50);
      setState("processing");

      const generateRes = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cvText: text }),
      });

      if (!generateRes.ok) {
        const data = await generateRes.json();
        throw new Error(data.error || "Generation failed");
      }

      const { id } = await generateRes.json();
      setProgress(100);

      setTimeout(() => {
        router.push(`/portfolio/${id}`);
      }, 500);
    } catch (err) {
      clearInterval(progressInterval);
      setError(err instanceof Error ? err.message : "Something went wrong");
      setState("error");
    }
  }, [router]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setState("idle");
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setState("dragging");
  }, []);

  const handleDragLeave = useCallback(() => {
    setState("idle");
  }, []);

  const isProcessing = state === "uploading" || state === "processing";

  return (
    <div className="relative min-h-screen flex items-center justify-center overflow-hidden">
      {/* Background */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-gradient-to-b from-primary/8 via-secondary/4 to-transparent rounded-full blur-3xl pointer-events-none" />

      <div className="relative z-10 w-full max-w-2xl mx-auto px-6">
        {/* Back */}
        <motion.a
          href="/"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="inline-flex items-center gap-2 text-text-secondary hover:text-foreground text-sm mb-8 transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          Back to home
        </motion.a>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="space-y-6"
        >
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold">Upload your CV</h1>
            <p className="text-text-secondary mt-2">
              Drop your PDF resume and watch the magic happen
            </p>
          </div>

          {/* Upload Area */}
          <AnimatePresence mode="wait">
            {isProcessing ? (
              <motion.div
                key="processing"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="glass rounded-2xl p-12 glow-primary"
              >
                <div className="text-center space-y-6">
                  {/* Animated Orb */}
                  <div className="relative w-24 h-24 mx-auto">
                    <div className="absolute inset-0 rounded-full bg-gradient-to-br from-primary to-accent animate-spin" style={{ animationDuration: "3s" }} />
                    <div className="absolute inset-1 rounded-full bg-surface" />
                    <div className="absolute inset-3 rounded-full bg-gradient-to-br from-primary/50 to-accent/50 animate-pulse" />
                  </div>

                  <div>
                    <p className="font-semibold text-lg">
                      {state === "uploading" ? "Analyzing your CV..." : "Generating portfolio..."}
                    </p>
                    <p className="text-text-secondary text-sm mt-1">
                      {state === "uploading"
                        ? "Extracting information from your resume"
                        : "AI is creating your premium portfolio"}
                    </p>
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full max-w-xs mx-auto">
                    <div className="h-1.5 bg-surface-light rounded-full overflow-hidden">
                      <motion.div
                        className="h-full bg-gradient-to-r from-primary to-accent rounded-full"
                        initial={{ width: "0%" }}
                        animate={{ width: `${progress}%` }}
                        transition={{ duration: 0.3 }}
                      />
                    </div>
                    <p className="text-xs text-text-secondary mt-2">{progress}%</p>
                  </div>

                  <p className="text-xs text-text-secondary">{fileName}</p>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="upload"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                className={`relative glass rounded-2xl p-12 text-center cursor-pointer transition-all group ${
                  state === "dragging"
                    ? "border-primary/50 glow-primary scale-[1.02]"
                    : "hover:border-primary/30"
                } ${state === "error" ? "border-red-500/30" : ""}`}
                onClick={() => {
                  const input = document.createElement("input");
                  input.type = "file";
                  input.accept = ".pdf";
                  input.onchange = (e) => {
                    const file = (e.target as HTMLInputElement).files?.[0];
                    if (file) handleFile(file);
                  };
                  input.click();
                }}
              >
                <div className="space-y-4">
                  {/* Upload Icon */}
                  <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-primary/10 to-accent/10 border border-primary/20 flex items-center justify-center group-hover:scale-110 transition-transform">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary">
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" strokeLinecap="round" />
                      <polyline points="17,8 12,3 7,8" strokeLinecap="round" strokeLinejoin="round" />
                      <line x1="12" y1="3" x2="12" y2="15" strokeLinecap="round" />
                    </svg>
                  </div>

                  <div>
                    <p className="font-semibold text-lg">
                      {state === "dragging" ? "Drop it here!" : "Drop your PDF here"}
                    </p>
                    <p className="text-text-secondary text-sm mt-1">
                      or click to browse • PDF up to 10MB
                    </p>
                  </div>

                  {state === "error" && (
                    <motion.p
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="text-red-400 text-sm"
                    >
                      {error}
                    </motion.p>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Info */}
          <div className="flex items-start gap-3 p-4 rounded-xl bg-surface/50 border border-border">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary mt-0.5 shrink-0">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4M12 8h.01" strokeLinecap="round" />
            </svg>
            <p className="text-xs text-text-secondary leading-relaxed">
              Your CV is processed securely. We extract text content to generate your portfolio.
              The PDF is not stored after processing.
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
