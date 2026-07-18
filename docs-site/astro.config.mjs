// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://brownjuly2003-code.github.io',
  base: '/ab-test-research-designer/',
  integrations: [
    starlight({
      title: 'AB Test Research Designer',
      description:
        'Static codebase docs for the AB_TEST experiment runner, statistical tests, notifier, dashboard, and deployment contracts.',
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/brownjuly2003-code/ab-test-research-designer',
        },
      ],
      // No global editLink: guide pages are generated copies (sync-docs.mjs
      // stamps a per-page editUrl pointing at the canonical docs/ source);
      // fully generated pages (routes/config/experiments) have nothing to edit.
      sidebar: [
        { label: 'Home', slug: 'index' },
        {
          label: 'Architecture',
          items: [
            { label: 'Overview', slug: 'architecture' },
            { label: 'API routes catalog', slug: 'architecture/routes' },
            { label: 'Experiment catalog', slug: 'architecture/experiments' },
            { label: 'Configuration matrix', slug: 'architecture/config' },
            { label: 'Repository architecture', slug: 'guides/architecture' },
          ],
        },
        {
          label: 'Operations',
          items: [
            { label: 'Runbook', slug: 'guides/runbook' },
            { label: 'Deploy', slug: 'guides/deploy' },
            { label: 'Release checklist', slug: 'guides/release_checklist' },
            { label: 'Rules', slug: 'guides/rules' },
          ],
        },
        {
          label: 'Plans & history',
          items: [
            { label: 'History', slug: 'guides/history' },
            { label: 'CHANGELOG', slug: 'guides/changelog' },
            { label: 'Release notes v1.1.0', slug: 'guides/release_notes_v1-1-0' },
            { label: 'Release notes v1.2.0', slug: 'guides/release_notes_v1-2-0' },
            { label: 'Release notes v1.3.0', slug: 'guides/release_notes_v1-3-0' },
          ],
        },
        {
          label: 'Research',
          items: [
            { label: 'Grey-market subscriptions', slug: 'guides/research-grey-market-digital-subscriptions' },
            { label: 'Case-study fixture', slug: 'guides/case-studies/readme' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'API reference', slug: 'guides/api' },
            { label: 'Release notes v1.0.0', slug: 'guides/release_notes_v1-0-0' },
          ],
        },
      ],
      customCss: ['./src/assets/custom.css'],
    }),
  ],
});
