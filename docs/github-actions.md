# GitHub Actions snippet (documentation only)

Do **not** commit this as `.github/workflows/` in the agent-docs-lint repo unless you have workflow scope.
Copy into *your* project's workflows:

```yaml
name: agent-docs-lint

on:
  pull_request:
  push:
    branches: [main]

jobs:
  lint-agent-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install git+https://github.com/hrtaym1114-github/agent-docs-lint.git
      - run: agent-docs-lint .
```
