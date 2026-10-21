import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://alder.shop',
  integrations: [react(), sitemap()],
  prefetch: true,
  image: {
    domains: ['images.unsplash.com', 'images.pexels.com'],
  },
});
