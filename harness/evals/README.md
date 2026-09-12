# Frozen evaluation suites

Evaluation suites in this directory are release evidence, not implementation hints.

Rules:

1. A feature WorkPackage may select a known suite but may not edit that suite.
2. A harness self-improvement candidate is evaluated against the exact same suite hash as its baseline.
3. The suite records the validity risks it is designed to probe.
4. Eval commands are owned by the code-side registry (`astermax.harness.evals.EVAL_REGISTRY`); YAML cannot inject commands.
5. Mandatory-case failure cannot be compensated by a better aggregate score.
6. Changes to frozen evals require a separate human-reviewed WorkPackage and establish a new baseline rather than rewriting the old comparison.

This separation is intentional: the system being optimized must not be able to silently rewrite its own judge.
