import argparse
import json
import sys
from pathlib import Path

from .core import DraftError, generate, load_json, requirements_from
from .providers import FixtureProvider, LlamaProvider


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Draft functional QA cases from acceptance criteria"
    )
    parser.add_argument("requirements", type=Path)
    parser.add_argument("--provider", choices=("fixture", "llama"), required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--origin", default="http://127.0.0.1:18081")
    parser.add_argument("--model", default="qwen-qa")
    args = parser.parse_args(argv)
    if args.provider == "fixture" and args.fixture is None:
        parser.error("--fixture is required for the fixture provider")
    try:
        requirements = requirements_from(load_json(args.requirements))
        provider = (
            FixtureProvider(load_json(args.fixture))
            if args.provider == "fixture"
            else LlamaProvider(args.origin, args.model)
        )
        result = generate(requirements, provider)
    except (OSError, DraftError) as exc:
        print(f"caseforge: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
