# AI Test Case Generator

Draft positive, negative, and boundary test cases for a list of acceptance requirements. Each draft carries a stable ID, requirement reference, explicit action, and observable expected result.

## Run the demo

Use Python 3.11 or later. The CLI and unit tests use the standard library.

```sh
python -m caseforge examples/requirements.json --provider fixture --fixture examples/recorded-drafts.json
python -m unittest discover -s tests -v
```

The fixture provider uses bundled sample responses tied to the exact input statements. It keeps CI reproducible. To generate drafts for your own requirements, use a local language model.

### Run with a local LLM

Start [llama.cpp](https://github.com/ggml-org/llama.cpp/tree/master/tools/server) with an instruction model such as [Qwen2.5-0.5B-Instruct GGUF](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF). The model is downloaded separately.

```sh
llama-server -m qwen2.5-0.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 18081 --alias qwen-qa -c 2048
python -m caseforge examples/grounded-requirements.json --provider llama
```

Pass `--origin` and `--model` to use a different numeric loopback port or model alias. For new input, save a JSON array of objects with `id` and `statement` fields. Add an `integer_constraint` with bounds and explicit accepted and rejected outcomes to control the values and oracles. The [grounded example](examples/grounded-requirements.json) uses a midpoint, a value just over the upper limit, and the exact upper limit. With prose alone the model drafts the complete case.

## Design

| Component | Responsibility |
| --- | --- |
| `caseforge/core.py` | Validate requirements and drafts, assign case IDs, and calculate partition counts |
| `caseforge/providers.py` | Use a deterministic fixture or send a schema-constrained request to a loopback llama.cpp server |
| `caseforge/__main__.py` | Write a complete JSON batch or fail with a clear error |
| `tests/` | Exercise the CLI, JSON validation, coverage checks, and the HTTP provider contract |

In grounded mode the model writes scenario titles and the application derives the actions and expected results from explicit constraints. In prose mode it validates schema and coverage categories, with human review needed to verify the model's proposed values and outcomes. Both modes attach stable IDs and mark every case `draft`. Each requirement yields three cases, so add separate targeted checks when you need more partitions.

GitHub Actions tests the deterministic path and uploads a sample case bundle. See [execution evidence](reports/EXECUTION.md).
