import { defineConfig, loadEnv, type ProxyOptions } from 'vite';
import react from '@vitejs/plugin-react';

// Specific routes must precede /api. Shared auth/guest remains on the common host.
export function createApiProxy(env: Record<string, string> = {}): Record<string, ProxyOptions> {
  const ads = env.VITE_ADS_API_TARGET || 'http://127.0.0.1:8000';
  const recommendation = env.VITE_RECOMMENDATION_API_TARGET || 'http://127.0.0.1:8001';
  return {
    '^/api/(?:ads(?:[/?]|$)|ad-events(?:[/?]|$)|ad-deliveries/|admin/(?:ads|ad-assets)(?:[/?]|$))': {
      target: ads, proxyTimeout: 5000,
    },
    '/api': { target: recommendation, proxyTimeout: 5000 },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: { proxy: createApiProxy({ ...loadEnv(mode, process.cwd(), 'VITE_'), ...process.env } as Record<string, string>) },
}));
