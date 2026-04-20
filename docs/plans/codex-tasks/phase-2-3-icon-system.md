# Task 2.3: Replace inline SVGs with Lucide React

**Phase:** 2 — Visual transformation  
**Priority:** Medium  
**Depends on:** nothing  
**Effort:** ~2h

---

## Context

Read these files before starting:
- `app/frontend/src/components/Icon.tsx` (205 lines — 12 inline SVG icons)
- Search for all `<Icon` usages in the codebase

Current problem: 12 inline SVG icons defined in `Icon.tsx` with inconsistent stroke weight and optical size.
Different icons were taken from different sources — no visual consistency.

---

## Goal

Replace all 12 inline SVG icons with Lucide React components.
Keep the `<Icon>` wrapper API so all existing usages don't change.

---

## Steps

### Step 1: Install Lucide React

```bash
cd app/frontend && npm install lucide-react
```

Verify: `lucide-react` in `package.json`.

### Step 2: Map existing icons to Lucide equivalents

Current icons in `Icon.tsx` and their Lucide replacements:

| Current name | Lucide component |
|---|---|
| `activity` / `health` | `Activity` |
| `check` / `checkmark` | `Check` |
| `chevron-right` | `ChevronRight` |
| `clock` | `Clock` |
| `code` | `Code2` |
| `download` / `export` | `Download` |
| `file-text` | `FileText` |
| `info` | `Info` |
| `plus` | `Plus` |
| `search` | `Search` |
| `trash` / `delete` | `Trash2` |
| `alert` / `warning` | `AlertTriangle` |
| `settings` | `Settings` |
| `save` | `Save` |
| `upload` / `import` | `Upload` |
| `refresh` | `RefreshCw` |
| `archive` | `Archive` |
| `history` | `History` |
| `compare` | `GitCompare` |
| `copy` | `Copy` |
| `x` / `close` | `X` |
| `external-link` | `ExternalLink` |

### Step 3: Rewrite `Icon.tsx`

Replace all inline SVG definitions with Lucide imports:

```tsx
import {
  Activity, Check, ChevronRight, Clock, Code2, Download,
  FileText, Info, Plus, Search, Trash2, AlertTriangle,
  Settings, Save, Upload, RefreshCw, Archive, History,
  Copy, X, ExternalLink, Moon, Sun, Monitor, BarChart3,
  TrendingUp, Shield, Sliders, Beaker, GitCompare
} from 'lucide-react';

const ICON_MAP = {
  activity: Activity,
  check: Check,
  'chevron-right': ChevronRight,
  clock: Clock,
  code: Code2,
  download: Download,
  'file-text': FileText,
  info: Info,
  plus: Plus,
  search: Search,
  trash: Trash2,
  alert: AlertTriangle,
  settings: Settings,
  save: Save,
  upload: Upload,
  refresh: RefreshCw,
  archive: Archive,
  history: History,
  compare: GitCompare,
  copy: Copy,
  close: X,
  'external-link': ExternalLink,
  moon: Moon,
  sun: Sun,
  monitor: Monitor,
  chart: BarChart3,
  trending: TrendingUp,
  shield: Shield,
  sliders: Sliders,
  beaker: Beaker,
} as const;

type IconName = keyof typeof ICON_MAP;

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  'aria-hidden'?: boolean;
  'aria-label'?: string;
}

export function Icon({ name, size = 16, className, ...rest }: IconProps) {
  const LucideIcon = ICON_MAP[name];
  if (!LucideIcon) {
    console.warn(`Icon "${name}" not found`);
    return null;
  }
  return <LucideIcon size={size} className={className} strokeWidth={1.5} {...rest} />;
}
```

### Step 4: Verify all existing `<Icon name="...">` usages still work

Search for all usages:
```
grep -r '<Icon' app/frontend/src/ --include="*.tsx"
```

For each usage, ensure the `name` prop value exists in `ICON_MAP`.
If any icon name is not in the map, add the Lucide equivalent.

### Step 5: Update icon names used in the codebase if needed

If any existing code uses icon names that don't match the new map keys, update the callsites (not the component) to use the correct name.

For example, if `SidebarPanel.tsx` uses `<Icon name="delete">` and the map has `trash`, update SidebarPanel to use `name="trash"`.

### Step 6: Clean up old SVG paths

After verifying all tests pass, delete all the inline SVG path data from `Icon.tsx` — they should be fully replaced by Lucide imports.

---

## Verify

- [ ] `npm install` completes without error
- [ ] `npm run build` exits 0
- [ ] `npm test` passes all 64 tests
- [ ] `npx tsc --noEmit` exits 0
- [ ] Visual check: icons render at consistent size and stroke weight in browser
- [ ] No `console.warn('Icon "..." not found')` in browser console
- [ ] Bundle size: `npm run build` — gzip JS increase should be < 5KB (Lucide is tree-shakeable)
- [ ] `grep -r "viewBox" app/frontend/src/components/Icon.tsx` returns nothing (old SVGs removed)

---

## Constraints

- Keep the `<Icon name="..." size={N}>` API unchanged — do NOT change callsites to import Lucide directly
- `strokeWidth={1.5}` must be set globally in the Icon wrapper (consistent optical weight)
- Do NOT add any icons that aren't already used — keep the bundle lean (only import used icons)
- After this task, adding a new icon = add 1 import + 1 entry in ICON_MAP in `Icon.tsx`
