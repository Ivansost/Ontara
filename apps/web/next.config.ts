import type { NextConfig } from 'next';
const config: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  allowedDevOrigins: ['127.0.0.1'],
  experimental: { cpus: 2, webpackMemoryOptimizations: true },
};
export default config;
