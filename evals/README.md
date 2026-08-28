# Evaluation harness

`run_eval.py` copies each fixture into a fresh temporary workspace and runs five real-model tasks
three times by default. It records task verification, tool success, self-correction, token use,
latency, memory pollution, unexpected skill activation, and dangerous-command leakage.

Validate fixtures without credentials:

```text
python evals/run_eval.py --dry-run
```

Run the acceptance evaluation with credentials supplied only through the environment:

```text
python evals/run_eval.py --model deepseek-chat --output eval-results.json
```

The command exits unsuccessfully when the thresholds documented in the project plan are missed.
Generated results can contain model output and are intentionally not committed.
