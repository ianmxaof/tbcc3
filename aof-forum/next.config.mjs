/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // Dev: allow both hostname styles so /_next assets work when the app is opened as 127.0.0.1 vs localhost.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
