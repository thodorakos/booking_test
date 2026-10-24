import { URL } from 'node:url';
import process from 'node:process';
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import { loadEnv } from 'vite';

const { PUBLIC_API_URL } = loadEnv(process.env.NODE_ENV || 'production', process.cwd(), 'PUBLIC_');
const apiOrigin = new URL(PUBLIC_API_URL || 'http://localhost:8787').origin;

export default defineConfig({
  site: 'https://alder.shop',
  integrations: [react(), sitemap({ filter: (page) => !['/admin', '/manage'].includes(new URL(page).pathname.replace(/\/$/, '')) })],
  prefetch: true,
  security: {
    csp: {
      directives: [
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-src 'none'",
        "form-action 'self'",
        "img-src 'self' https://images.unsplash.com https://images.pexels.com data:",
        `connect-src 'self' ${apiOrigin}`,
        "font-src 'self'",
      ],
      styleDirective: { resources: ["'self'", { resource: "'unsafe-inline'", kind: 'attribute' }] },
    },
  },
  image: {
    domains: ['images.unsplash.com', 'images.pexels.com'],
  },
});
