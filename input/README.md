# Input Directory

Put your own input briefs here. Both markdown (`.md`, recommended) and YAML
(`.yaml`/`.yml`) are accepted. The files in `examples/` are samples you can
copy and modify.

The recommended workflow is to copy the markdown template:

```
cp examples/templates/input-brief-template.md input/my-product.md
```

Open `input/my-product.md`, fill in each section, then run:

```
uv run pm_agent_system full-pipeline input/my-product.md
```

YAML still works for developers and automation:

```
uv run pm_agent_system full-pipeline input/my-product.yaml
```

This directory is gitignored (except this README) so your input files — which
may contain company-specific context — are never accidentally committed.

See `examples/input-brief-example.md` (markdown) or `examples/input.yaml` (YAML)
for completed examples and field descriptions.
