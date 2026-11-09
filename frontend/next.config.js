/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // This application serves document previews through the backend, not next/image.
  images: { unoptimized: true },
};

module.exports = nextConfig;
