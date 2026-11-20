# Execution evidence

All 13 unit, HTTP adapter, and CLI tests passed on Python 3.14.4. Ruff passed. The fixture CLI emitted six drafts for two requirements.

Live runs used llama.cpp b12248 on CPU with [Qwen2.5 0.5B Instruct Q4_K_M](https://ollama.com/library/qwen2.5:0.5b-instruct-q4_K_M) and [SmolLM2 360M Instruct Q4_K_M](https://ollama.com/library/smollm2:360m-instruct-q4_K_M). The runtime and both model files matched their upstream SHA-256 digests.

Both grounded runs produced six valid drafts from two requirements. The checkout inputs were 3, 6, and 5. The discount inputs were 10, 21, and 20. The application preserved the supplied rejection outcomes for 6 and 21. Qwen adapted two titles using the stated bounds. SmolLM2 echoed the grounded title examples.

The prose-only Qwen run was rejected for duplicate case titles. That shows the validator catches one type of low-quality draft. Use grounded constraints for a repeatable baseline and review any model-generated content before adopting it.

See the [Qwen output](llama-qwen-sample.json) and [SmolLM2 output](llama-smollm2-sample.json). Reproduce these runs with the [grounded sample requirements](../examples/grounded-requirements.json), setting `--model` to the model alias on your loopback server.
