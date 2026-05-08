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
      editLink: {
        baseUrl:
          'https://github.com/brownjuly2003-code/ab-test-research-designer/edit/main/docs-site/',
      },
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
            { label: 'Latest HF sync report', slug: 'guides/plans/2026-04-23-hf-sync-post-mc-report' },
          ],
        },
        {
          label: 'Research',
          items: [
            { label: 'Grey-market subscriptions', slug: 'guides/research-grey-market-digital-subscriptions' },
            { label: 'Case-study fixture', slug: 'guides/case-studies/readme' },
            { label: 'Advanced visualization report', slug: 'guides/plans/2026-04-22-advanced-viz-report' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'API reference', slug: 'guides/api' },
            { label: 'Release notes v1.0.0', slug: 'guides/release_notes_v1-0-0' },
            { label: 'Postgres backend report', slug: 'guides/plans/2026-04-23-postgres-backend-report' },
            { label: 'Public API report', slug: 'guides/plans/2026-04-22-public-api-report' },
          ],
        },
      ],
      customCss: ['./src/assets/custom.css'],
    }),
  ],
});
