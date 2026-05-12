import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["@prisma/client", "prisma", "better-sqlite3", "pdf-parse"],
};

export default nextConfig;
