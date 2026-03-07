# Recommended File Tree

```text
ab-test-research-designer/
  docs/
    IMPLEMENTATION_SPEC.md
    DATA_CONTRACTS.md
    AGENT_INSTRUCTIONS.md
    BUILD_PLAN.md
    PROJECT_CONTEXT.md
    progress.md

  frontend/
    src/
      app/
      components/
      features/
        experiment-form/
        results/
        saved-projects/
      lib/
      api/
      types/
      pages/
      styles/
    package.json
    tsconfig.json
    vite.config.ts

  backend/
    app/
      main.py
      config.py
      api/
        routes/
          calculate.py
          design.py
          llm.py
          projects.py
          export.py
      schemas/
        project.py
        metrics.py
        calculations.py
        report.py
        warnings.py
      services/
        calculations_service.py
        design_service.py
        export_service.py
        project_service.py
      stats/
        binary.py
        continuous.py
        duration.py
      rules/
        engine.py
        catalog.py
      llm/
        adapter.py
        prompt_builder.py
        parser.py
      storage/
        db.py
        models.py
        repository.py
      utils/
    tests/
      test_binary_calculations.py
      test_continuous_calculations.py
      test_rules_engine.py
      test_api_calculate.py
      test_api_design.py
    requirements.txt
    pyproject.toml

  exports/
  data/
  scripts/
  .env
  .gitignore
  README.md
```

## Notes
- `docs/progress.md` обновляется после каждой фазы.
- Реальная интеграция с оркестратором должна лежать в `backend/app/llm/adapter.py`.
- Путь `D:\Perplexity_Orchestrator2` не должен быть жестко зашит без конфигурации.
