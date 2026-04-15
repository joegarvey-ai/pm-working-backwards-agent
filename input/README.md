# Input Directory

Put your own input YAML files here. The files in `examples/` are samples you
can copy and modify. Once you've customized an input file for your product
problem, save it here and run:

```
uv run pm_agent_system full-pipeline input/my-product.yaml
```

This directory is gitignored (except this README) so your input files — which
may contain company-specific context — are never accidentally committed.

See `examples/input.yaml` for the expected format and field descriptions.
