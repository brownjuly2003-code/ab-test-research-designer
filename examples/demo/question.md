# ASOS benchmark question

For the public ASOS experiment `d53f0e`, does treatment change the terminal
response rate of published binary metric 1 relative to control?

This is a retrospective reproducibility question, not a product decision. The
public extract contains aggregate checkpoints but not the original protocol,
metric meaning, or exposure events. The demo therefore keeps those limitations
explicit and uses the benchmark only to exercise Trialmark's frozen protocol,
preflight, evidence, and human-decision flow.

Before the corrected run, the demo injects three independent faults:

1. the primary metric is also declared as a guardrail;
2. aggregate assignment counts are skewed to 90/10, simulating a bad seed
   against the frozen 50/50 allocation;
3. one aggregate event is declared beyond the allowed lateness window.

Each scenario must produce its named blocking finding. Only the unchanged
protocol below may reach analysis and a reviewable `.tmk` decision bundle.
