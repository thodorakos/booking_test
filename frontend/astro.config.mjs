import { URL } from 'node:url';
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://alder.shop',
  integrations: [react(), sitemap({ filter: (page) => !['/admin', '/manage'].includes(new URL(page).pathname.replace(/\/$/, '')) })],
  prefetch: true,
  image: {
    domains: ['images.unsplash.com', 'images.pexels.com'],
  },
});
