# Data Contracts

## 1. Frontend form payload

```json
{
  "project": {
    "project_name": "Checkout redesign",
    "domain": "e-commerce",
    "product_type": "web app",
    "platform": "web",
    "market": "US",
    "project_description": "We want to test a simplified checkout flow."
  },
  "hypothesis": {
    "change_description": "Reduce checkout from 4 steps to 2",
    "target_audience": "new users on web",
    "business_problem": "checkout abandonment is high",
    "hypothesis_statement": "If we simplify checkout for new users, purchase conversion will increase because the flow becomes easier.",
    "what_to_validate": "impact on conversion",
    "desired_result": "statistically and practically meaningful uplift"
  },
  "setup": {
    "experiment_type": "ab",
    "randomization_unit": "user",
    "traffic_split": [50, 50],
    "expected_daily_traffic": 12000,
    "audience_share_in_test": 0.6,
    "variants_count": 2,
    "inclusion_criteria": "new users only",
    "exclusion_criteria": "internal staff"
  },
  "metrics": {
    "primary_metric_name": "purchase_conversion",
    "metric_type": "binary",
    "baseline_value": 0.042,
    "expected_uplift_pct": 8,
    "mde_pct": 5,
    "alpha": 0.05,
    "power": 0.8,
    "std_dev": null,
    "secondary_metrics": ["add_to_cart_rate"],
    "guardrail_metrics": ["payment_error_rate", "refund_rate"]
  },
  "constraints": {
    "seasonality_present": true,
    "active_campaigns_present": false,
    "returning_users_present": true,
    "interference_risk": "medium",
    "technical_constraints": "legacy event logging",
    "legal_or_ethics_constraints": "none",
    "known_risks": "tracking quality",
    "deadline_pressure": "medium",
    "long_test_possible": true
  },
  "additional_context": {
    "llm_context": "Previous tests showed mixed results. Team worries about event quality and segmentation."
  }
}
```

## 2. Calculation request schema

```json
{
  "metric_type": "binary",
  "baseline_value": 0.042,
  "mde_pct": 5,
  "alpha": 0.05,
  "power": 0.8,
  "expected_daily_traffic": 12000,
  "audience_share_in_test": 0.6,
  "traffic_split": [50, 50],
  "variants_count": 2,
  "std_dev": null
}
```

Validation notes:

- `variants_count` must stay within `2..10`
- `traffic_split` length must match `variants_count`
- for `metric_type = "continuous"`, `std_dev` must be present and strictly positive

## 3. Calculation response schema

```json
{
  "calculation_summary": {
    "metric_type": "binary",
    "baseline_value": 0.042,
    "mde_pct": 5,
    "mde_absolute": 0.0021,
    "alpha": 0.05,
    "power": 0.8
  },
  "results": {
    "sample_size_per_variant": 41234,
    "total_sample_size": 82468,
    "effective_daily_traffic": 7200,
    "estimated_duration_days": 12
  },
  "assumptions": [
    "Traffic assumed stable during the test window.",
    "No major implementation breaks expected."
  ],
  "warnings": [
    {
      "code": "SEASONALITY_PRESENT",
      "severity": "medium",
      "message": "Seasonality is present. Cover at least one full weekly cycle."
    }
  ]
}
```

## 4. Design generation response schema

```json
{
  "executive_summary": "...",
  "calculations": {
    "sample_size_per_variant": 41234,
    "total_sample_size": 82468,
    "estimated_duration_days": 12,
    "assumptions": ["..."]
  },
  "experiment_design": {
    "variants": [
      {"name": "A", "description": "current checkout"},
      {"name": "B", "description": "simplified checkout"}
    ],
    "randomization_unit": "user",
    "traffic_split": [50, 50],
    "target_audience": "new users on web",
    "inclusion_criteria": "new users only",
    "exclusion_criteria": "internal staff",
    "recommended_duration_days": 12,
    "stopping_conditions": [
      "planned duration reached",
      "critical instrumentation failure"
    ]
  },
  "metrics_plan": {
    "primary": ["purchase_conversion"],
    "secondary": ["add_to_cart_rate"],
    "guardrail": ["payment_error_rate", "refund_rate"],
    "diagnostic": ["assignment_rate", "checkout_step_completion"]
  },
  "risks": {
    "statistical": ["..."],
    "product": ["..."],
    "technical": ["..."],
    "operational": ["..."]
  },
  "recommendations": {
    "before_launch": ["..."],
    "during_test": ["..."],
    "after_test": ["..."]
  },
  "open_questions": ["..."]
}
```

## 4.1 Combined analysis response schema

```json
{
  "calculations": {
    "calculation_summary": {
      "metric_type": "binary",
      "baseline_value": 0.042,
      "mde_pct": 5,
      "mde_absolute": 0.0021,
      "alpha": 0.05,
      "power": 0.8
    },
    "results": {
      "sample_size_per_variant": 41234,
      "total_sample_size": 82468,
      "effective_daily_traffic": 7200,
      "estimated_duration_days": 12
    },
    "assumptions": ["..."],
    "warnings": [
      {
        "code": "LONG_DURATION",
        "severity": "high",
        "message": "...",
        "source": "rules_engine"
      }
    ]
  },
  "report": {
    "executive_summary": "...",
    "calculations": {
      "sample_size_per_variant": 41234,
      "total_sample_size": 82468,
      "estimated_duration_days": 12,
      "assumptions": ["..."]
    },
    "experiment_design": {
      "variants": [{"name": "A", "description": "current checkout"}],
      "randomization_unit": "user",
      "traffic_split": [50, 50],
      "target_audience": "new users on web",
      "inclusion_criteria": "new users only",
      "exclusion_criteria": "internal staff",
      "recommended_duration_days": 12,
      "stopping_conditions": ["planned duration reached", "critical instrumentation failure"]
    },
    "metrics_plan": {
      "primary": ["purchase_conversion"],
      "secondary": ["add_to_cart_rate"],
      "guardrail": ["payment_error_rate"],
      "diagnostic": ["assignment_rate"]
    },
    "risks": {
      "statistical": ["..."],
      "product": ["..."],
      "technical": ["..."],
      "operational": ["..."]
    },
    "recommendations": {
      "before_launch": ["..."],
      "during_test": ["..."],
      "after_test": ["..."]
    },
    "open_questions": ["..."]
  },
  "advice": {
    "available": false,
    "provider": "local_orchestrator",
    "model": "Claude Sonnet 4.6",
    "advice": null,
    "raw_text": null,
    "error": "offline",
    "error_code": "request_error"
  }
}
```

## 5. Warning object

```json
{
  "code": "LONG_DURATION",
  "severity": "high",
  "message": "Estimated duration exceeds 56 days. Consider increasing traffic or relaxing MDE.",
  "source": "rules_engine"
}
```

## 6. API endpoints

### POST `/api/v1/calculate`
Validation: request schema violations return `422 Unprocessable Entity`.
Назначение: вернуть deterministic calculations и warnings.

### POST `/api/v1/design`
Validation: request schema violations return `422 Unprocessable Entity`.
Назначение: собрать полный report из user input + calculations + warnings + optional LLM advice.

### POST `/api/v1/llm/advice`
Назначение: отдельно запросить AI advice.

### GET `/api/v1/projects`
Список проектов.

### POST `/api/v1/projects`
Validation: uses the same structured payload as `POST /api/v1/design`.
Создание проекта.

### GET `/api/v1/projects/{project_id}`
Чтение проекта.

### PUT `/api/v1/projects/{project_id}`
Validation: uses the same structured payload as `POST /api/v1/design`.
Обновление проекта.

### POST `/api/v1/export/markdown`
Экспорт markdown.

### POST `/api/v1/export/html`
Экспорт html.

## 7. LLM adapter request contract

```json
{
  "system_role": "experiment_design_advisor",
  "project_context": {"...": "..."},
  "calculation_results": {"...": "..."},
  "warnings": [{"...": "..."}],
  "response_format": {
    "brief_assessment": "string",
    "key_risks": ["string"],
    "design_improvements": ["string"],
    "metric_recommendations": ["string"],
    "interpretation_pitfalls": ["string"],
    "additional_checks": ["string"]
  }
}
```

## 8. LLM adapter response contract

```json
{
  "brief_assessment": "The test is feasible, but event quality is a risk.",
  "key_risks": [
    "Instrumentation quality may bias results.",
    "Returning users may contaminate exposure."
  ],
  "design_improvements": [
    "Add assignment logging validation before launch."
  ],
  "metric_recommendations": [
    "Track checkout step completion as a diagnostic metric."
  ],
  "interpretation_pitfalls": [
    "Do not over-interpret early uplift in the first 1-2 days."
  ],
  "additional_checks": [
    "Verify equal exposure by traffic source."
  ]
}
```

## 9. Combined analysis endpoint

### POST `/api/v1/analyze`

Validation: request schema violations return `422 Unprocessable Entity`.

Purpose:

- return deterministic calculations
- return the deterministic report
- return optional AI advice in the same response payload

This is the preferred frontend analysis route because it replaces separate browser requests to:

- `POST /api/v1/calculate`
- `POST /api/v1/design`
- `POST /api/v1/llm/advice`

## 10. Project storage metadata

Saved project records now include storage metadata in both list and record responses:

```json
{
  "id": "project-id",
  "project_name": "Checkout redesign",
  "payload_schema_version": 1,
  "last_analysis_at": "2026-03-07T12:30:00+00:00",
  "last_exported_at": "2026-03-07T12:45:00+00:00",
  "has_analysis_snapshot": true,
  "created_at": "2026-03-07T10:00:00+00:00",
  "updated_at": "2026-03-07T10:15:00+00:00"
}
```

The full `GET /api/v1/projects/{project_id}` and `POST`/`PUT /api/v1/projects` record payload also includes:

```json
{
  "payload": {
    "project": {"project_name": "Checkout redesign"}
  }
}
```

## 11. Project activity endpoints

### POST `/api/v1/projects/{project_id}/analysis`

Request body: the same combined analysis object returned by `POST /api/v1/analyze`.

Purpose:

- persist the last successful combined analysis snapshot for a saved project
- stamp `last_analysis_at`
- set `has_analysis_snapshot=true`

### POST `/api/v1/projects/{project_id}/exports`

Request body:

```json
{
  "format": "markdown",
  "analysis_run_id": null
}
```

Purpose:

- stamp `last_exported_at` after a successful report export
- keep export tracking separate from report generation

## 12. Project history endpoint

### GET `/api/v1/projects/{project_id}/history`

Response shape:

```json
{
  "project_id": "project-id",
  "analysis_runs": [
    {
      "id": "analysis-run-id",
      "project_id": "project-id",
      "created_at": "2026-03-07T12:30:00+00:00",
      "summary": {
        "metric_type": "binary",
        "sample_size_per_variant": 41234,
        "total_sample_size": 82468,
        "estimated_duration_days": 12,
        "warnings_count": 1,
        "advice_available": false
      },
      "analysis": {
        "calculations": {"results": {"sample_size_per_variant": 41234}},
        "report": {"executive_summary": "..."},
        "advice": {"available": false}
      }
    }
  ],
  "export_events": [
    {
      "id": "export-event-id",
      "project_id": "project-id",
      "analysis_run_id": null,
      "format": "markdown",
      "created_at": "2026-03-07T12:45:00+00:00"
    }
  ]
}
```

Purpose:

- fetch saved-project analysis history without re-running the backend
- fetch export-event history separately from the current project summary fields

## 13. Project comparison endpoint

### GET `/api/v1/projects/compare`

Query params:

- `base_id`
- `candidate_id`

Response shape:

```json
{
  "base_project": {
    "id": "project-a",
    "project_name": "Checkout baseline",
    "analysis_run_id": "run-a",
    "primary_metric": "purchase_conversion",
    "total_sample_size": 82468,
    "estimated_duration_days": 12,
    "warning_codes": ["SEASONALITY_PRESENT"]
  },
  "candidate_project": {
    "id": "project-b",
    "project_name": "Checkout challenger",
    "analysis_run_id": "run-b",
    "primary_metric": "purchase_conversion",
    "total_sample_size": 91000,
    "estimated_duration_days": 15,
    "warning_codes": ["LONG_DURATION", "LOW_TRAFFIC"]
  },
  "deltas": {
    "sample_size_per_variant": 4266,
    "total_sample_size": 8532,
    "estimated_duration_days": 3,
    "warnings_count": 1
  },
  "shared_warning_codes": [],
  "base_only_warning_codes": ["SEASONALITY_PRESENT"],
  "candidate_only_warning_codes": ["LONG_DURATION", "LOW_TRAFFIC"],
  "summary": "Checkout challenger needs larger total sample size and a longer test window than Checkout baseline."
}
```

Purpose:

- compare two saved projects without re-running calculations
- use the latest persisted analysis snapshot for each project
- surface delta in size, duration, and warning footprint for frontend rendering
