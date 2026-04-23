# T7: Error Boundaries

**Phase:** BCG Phase 1
**Depends on:** T6 (ResultsPanel декомпозирован)
**Effort:** ~1.5h

## Context

Сейчас любой throw в chart-компоненте (Recharts, ForestPlot) роняет весь React subtree. Нужны два error boundary:
1. `ErrorBoundary` — generic, вокруг крупных блоков layout
2. `ChartErrorBoundary` — специфичный, показывает "Chart unavailable" + raw data

Читать:
- `archive/2026-04-23-bcg-planning-docs/BCG_plan.md` §1.4.1-1.4.3
- `src/App.tsx`, `src/components/results/*` (PowerCurveSection, ForestPlot)

## Goal

Добавить два error boundary, обернуть layout и chart-компоненты, покрыть тестами.

## Steps

### 1. `src/components/ErrorBoundary.tsx`

Class component:

```tsx
interface Props {
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state = { hasError: false, error: null };
  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
    // optional: console.error(error, info)
  }
  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="error-boundary-fallback">
          <h3>Something went wrong</h3>
          <button onClick={() => this.setState({ hasError: false, error: null })}>
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

Стили в `src/styles/components.css` (или inline module).

### 2. `src/components/ChartErrorBoundary.tsx`

Обёртка над `ErrorBoundary` с специфичным fallback:

```tsx
<ErrorBoundary fallback={
  <div className="chart-error">
    <p>Chart unavailable</p>
    {rawData ? <pre>{JSON.stringify(rawData, null, 2)}</pre> : null}
  </div>
}>
  {children}
</ErrorBoundary>
```

Prop `rawData?: unknown` для показа данных, если чарт не смог отрендериться.

### 3. Обернуть в `App.tsx`

```tsx
<ErrorBoundary><WizardPanel /></ErrorBoundary>
<ErrorBoundary><SidebarPanel /></ErrorBoundary>
```

Crash в sidebar не должен ронять wizard, и наоборот.

### 4. Обернуть chart-компоненты

В `src/components/results/`:
- `PowerCurveSection` → `<ChartErrorBoundary rawData={powerCurveData}>...</ChartErrorBoundary>`
- `ObservedResultsSection` (ForestPlot) → то же самое
- `SensitivitySection` (если внутри есть chart)

### 5. Тесты

`src/components/ErrorBoundary.test.tsx`:
- Компонент без ошибок → рендерит children
- Компонент throws → рендерит fallback
- Retry button сбрасывает state
- `onError` callback вызывается

`src/components/ChartErrorBoundary.test.tsx`:
- Throws внутри → "Chart unavailable" + pre с rawData

Тестовый компонент-броскун:
```tsx
function BrokenComponent(): never { throw new Error("boom"); }
```

### 6. Verify

```bash
cd app/frontend
npx vitest run src/components/ErrorBoundary.test.tsx src/components/ChartErrorBoundary.test.tsx
npx vitest run
npx tsc --noEmit
npm run build
```

Ручная проверка: временно бросить ошибку в PowerCurveSection (`throw new Error("test")`) → только chart показывает fallback, остальные секции живые, layout не сломан. Откатить.

## Done When

- [ ] `ErrorBoundary.tsx` + тесты
- [ ] `ChartErrorBoundary.tsx` + тесты
- [ ] `App.tsx` оборачивает WizardPanel и SidebarPanel
- [ ] Chart-компоненты обёрнуты в `ChartErrorBoundary`
- [ ] Все тесты зелёные

## Constraints

- Fallback UI — минимальный, без дизайнерских изысков (это уровень Phase 2)
- Не логировать в production — `console.error` только, никакой телеметрии (Sentry/PostHog — это Phase 3)
