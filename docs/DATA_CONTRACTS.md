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
Назначение: вернуть deterministic calculations и warnings.

### POST `/api/v1/design`
Назначение: собрать полный report из user input + calculations + warnings + optional LLM advice.

### POST `/api/v1/llm/advice`
Назначение: отдельно запросить AI advice.

### GET `/api/v1/projects`
Список проектов.

### POST `/api/v1/projects`
Создание проекта.

### GET `/api/v1/projects/{project_id}`
Чтение проекта.

### PUT `/api/v1/projects/{project_id}`
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
