# Contributing

Thanks for considering a contribution. This project is small and welcomes help from PMs, engineers, and writers alike.

## Ways to help

- **Report bugs.** Open a GitHub issue with the command you ran, the input you used (with secrets removed), and the full error text.
- **Improve the prompts.** The agent prompts in `src/pm_agent_system/config/agents.yaml` and `tasks.yaml` are the most important part of this system. If you can make them produce better output, open a PR.
- **Add a coding tool target.** The build spec agent currently supports Kiro, Claude Code, Cursor, and Lovable. If you use a different tool, add a renderer in `src/pm_agent_system/utils/render_build_spec.py`.
- **Write a better example.** The main example exists in two equivalent forms — `examples/input-brief-example.md` (markdown) and `examples/input.yaml` (YAML) — both describing a fictional self-service analytics dashboard for mid-market e-commerce merchants (conversion funnel reporting for Shopify/WooCommerce stores). The `examples/standalone-prfaq/` and `examples/standalone-brd/` subdirectories contain additional standalone-mode inputs. Real-world examples in different domains would help new users.
- **Improve the docs.** The README, SETUP, and GLOSSARY are written for non-technical PMs. If anything reads as jargon, fix it.

## How to submit a PR

1. Fork the repo.
2. Create a branch with a short, descriptive name (e.g., `add-bigcommerce-research-source`).
3. Make your change. Keep the diff focused.
4. If you changed code, run the smoke test (`uv run pm_agent_system research examples/input-brief-example.md`) to confirm nothing broke.
5. Open a PR with a short description of what you changed and why.

## Running tests

Install dev dependencies (one-time per environment) and run the suite:

```bash
uv sync --group dev
uv run pytest
```

The `dev` dependency group includes pytest. Older checkouts may still install
the legacy `test` extra (`uv pip install -e ".[test]"`); both paths work.

## Code style

Match what's already there. We use standard Python formatting (`ruff` if you have it installed). No hard rules beyond that.

## Be kind

This is an open-source project run by volunteers. Be patient, be specific, and assume good intent.
