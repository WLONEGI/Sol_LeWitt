import type { NextConfig } from "next";


const nextConfig: NextConfig = {
  output: 'standalone',
  compress: false,
  env: {
    // App Hosting injects FIREBASE_WEBAPP_CONFIG, but client-side code needs NEXT_PUBLIC_ prefixes.
    // We map them here so they are embedded at build time (or runtime if supported by Next.js output: standalone).
    ...(process.env.FIREBASE_WEBAPP_CONFIG ? (() => {
      try {
        const config = JSON.parse(process.env.FIREBASE_WEBAPP_CONFIG);
        return {
          NEXT_PUBLIC_FIREBASE_API_KEY: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || config.apiKey,
          NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || config.authDomain,
          NEXT_PUBLIC_FIREBASE_PROJECT_ID: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || config.projectId,
          NEXT_PUBLIC_FIREBASE_APP_ID: process.env.NEXT_PUBLIC_FIREBASE_APP_ID || config.appId,
        };
      } catch (e) {
        console.warn("Failed to parse FIREBASE_WEBAPP_CONFIG", e);
        return {};
      }
    })() : {}),
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer-when-downgrade" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },
          { key: "Cross-Origin-Embedder-Policy", value: "unsafe-none" },
        ],
      },
    ];
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'https://ai-slide-backend-1021289594562.asia-northeast1.run.app';
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
