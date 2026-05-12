"use client";

import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { useState, useEffect, useCallback, useRef } from "react";

interface PortfolioEntry {
  id: string;
  fullName: string;
  title: string;
  revoked: boolean;
  createdAt: string;
}

function getInitialToken(): string {
  if (typeof window !== "undefined") {
    return sessionStorage.getItem("admin_token") || "";
  }
  return "";
}

export default function AdminPage() {
  const [token, setToken] = useState(getInitialToken);
  const [authenticated, setAuthenticated] = useState(false);
  const [portfolios, setPortfolios] = useState<PortfolioEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchPortfolios = useCallback(async (adminToken: string) => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/portfolios", {
        headers: { "x-admin-token": adminToken },
      });
      if (!res.ok) {
        if (res.status === 401) throw new Error("Invalid admin token");
        throw new Error("Failed to fetch");
      }
      const data = await res.json();
      setPortfolios(data.portfolios);
      setAuthenticated(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
      setAuthenticated(false);
    }
    setLoading(false);
  }, []);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (token.trim()) fetchPortfolios(token.trim());
  };

  const toggleRevoke = async (id: string, currentRevoked: boolean) => {
    try {
      const res = await fetch(`/api/portfolios/${id}/revoke`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-admin-token": token,
        },
        body: JSON.stringify({ revoked: !currentRevoked }),
      });
      if (res.ok) {
        setPortfolios((prev) =>
          prev.map((p) =>
            p.id === id ? { ...p, revoked: !currentRevoked } : p
          )
        );
      }
    } catch {
      alert("Failed to update status");
    }
  };

  const initializedRef = useRef(false);
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    if (!token) return;
    const controller = new AbortController();
    fetch("/api/portfolios", {
      headers: { "x-admin-token": token },
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(res.status === 401 ? "Invalid admin token" : "Failed to fetch");
        return res.json();
      })
      .then((data) => {
        setPortfolios(data.portfolios);
        setAuthenticated(true);
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Error");
      });
    return () => controller.abort();
  }, [token]);

  useEffect(() => {
    if (authenticated && token) {
      sessionStorage.setItem("admin_token", token);
    }
  }, [authenticated, token]);

  return (
    <div className="min-h-screen bg-background relative">
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />

      <div className="relative z-10 max-w-5xl mx-auto px-6 py-12">
        <div className="flex items-center justify-between mb-8">
          <div>
            <Link
              href="/"
              className="text-sm text-text-secondary hover:text-foreground transition-colors mb-2 inline-block"
            >
              ← Back to home
            </Link>
            <h1 className="text-3xl font-bold">Admin Dashboard</h1>
            <p className="text-text-secondary text-sm mt-1">
              Manage all generated portfolios
            </p>
          </div>
          {authenticated && (
            <div className="text-sm px-3 py-1 rounded-full bg-green-500/10 text-green-400 border border-green-500/20">
              Authenticated
            </div>
          )}
        </div>

        <AnimatePresence mode="wait">
          {!authenticated ? (
            <motion.div
              key="login"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="max-w-md mx-auto"
            >
              <form onSubmit={handleLogin} className="glass rounded-2xl p-8 space-y-6">
                <div className="text-center">
                  <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center text-white text-xl mx-auto mb-4">
                    🔐
                  </div>
                  <h2 className="text-xl font-semibold">Admin Access</h2>
                  <p className="text-text-secondary text-sm mt-1">
                    Enter your admin token to continue
                  </p>
                </div>

                <div>
                  <input
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="Admin token"
                    className="w-full px-4 py-3 rounded-xl bg-surface border border-border text-foreground placeholder-text-secondary focus:outline-none focus:border-primary/50 transition-colors"
                    autoFocus
                  />
                </div>

                {error && (
                  <p className="text-red-400 text-sm text-center">{error}</p>
                )}

                <button
                  type="submit"
                  disabled={loading || !token.trim()}
                  className="w-full py-3 rounded-xl bg-primary text-white font-medium hover:bg-primary/90 transition-all disabled:opacity-50"
                >
                  {loading ? "Verifying..." : "Access Dashboard"}
                </button>
              </form>
            </motion.div>
          ) : (
            <motion.div
              key="dashboard"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              {/* Stats */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
                <div className="glass rounded-xl p-5">
                  <p className="text-text-secondary text-sm">Total Portfolios</p>
                  <p className="text-3xl font-bold mt-1">{portfolios.length}</p>
                </div>
                <div className="glass rounded-xl p-5">
                  <p className="text-text-secondary text-sm">Active</p>
                  <p className="text-3xl font-bold mt-1 text-green-400">
                    {portfolios.filter((p) => !p.revoked).length}
                  </p>
                </div>
                <div className="glass rounded-xl p-5">
                  <p className="text-text-secondary text-sm">Revoked</p>
                  <p className="text-3xl font-bold mt-1 text-red-400">
                    {portfolios.filter((p) => p.revoked).length}
                  </p>
                </div>
              </div>

              {/* Table */}
              <div className="glass rounded-2xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left px-6 py-4 text-xs font-medium text-text-secondary uppercase tracking-wider">
                          User
                        </th>
                        <th className="text-left px-6 py-4 text-xs font-medium text-text-secondary uppercase tracking-wider">
                          Created
                        </th>
                        <th className="text-left px-6 py-4 text-xs font-medium text-text-secondary uppercase tracking-wider">
                          Status
                        </th>
                        <th className="text-right px-6 py-4 text-xs font-medium text-text-secondary uppercase tracking-wider">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {portfolios.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="px-6 py-12 text-center text-text-secondary">
                            No portfolios generated yet
                          </td>
                        </tr>
                      ) : (
                        portfolios.map((p) => (
                          <tr
                            key={p.id}
                            className="border-b border-border/50 hover:bg-surface/50 transition-colors"
                          >
                            <td className="px-6 py-4">
                              <div>
                                <p className="font-medium text-sm">{p.fullName}</p>
                                <p className="text-xs text-text-secondary">{p.title}</p>
                              </div>
                            </td>
                            <td className="px-6 py-4 text-sm text-text-secondary">
                              {new Date(p.createdAt).toLocaleDateString("fr-FR", {
                                day: "numeric",
                                month: "short",
                                year: "numeric",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </td>
                            <td className="px-6 py-4">
                              <span
                                className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                  p.revoked
                                    ? "bg-red-500/10 text-red-400 border border-red-500/20"
                                    : "bg-green-500/10 text-green-400 border border-green-500/20"
                                }`}
                              >
                                {p.revoked ? "Revoked" : "Active"}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <a
                                  href={`/p/${p.id}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border hover:border-primary/50 text-text-secondary hover:text-foreground transition-all"
                                >
                                  View
                                </a>
                                <button
                                  onClick={() => toggleRevoke(p.id, p.revoked)}
                                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                                    p.revoked
                                      ? "bg-green-500/10 text-green-400 hover:bg-green-500/20"
                                      : "bg-red-500/10 text-red-400 hover:bg-red-500/20"
                                  }`}
                                >
                                  {p.revoked ? "Restore" : "Revoke"}
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
