import type { NextConfig } from 'next';
import { createRequire } from 'node:module';
const resolvePackage = createRequire(import.meta.url);
const livekitCommonJS = resolvePackage.resolve('livekit-client', { paths: [resolvePackage.resolve('@elevenlabs/client')] });
const config: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  allowedDevOrigins: ['127.0.0.1'],
  experimental: { cpus: 2, webpackMemoryOptimizations: true },
  webpack(config) {
    // This Next/Babel build rejects the SDK's named imports from LiveKit's
    // ESM distribution. Its official CommonJS build exports the same values.
    config.resolve.alias['livekit-client$'] = livekitCommonJS;
    return config;
  },
};
export default config;
