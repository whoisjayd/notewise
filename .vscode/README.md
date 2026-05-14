# VS Code Settings

`python.defaultInterpreterPath` points VS Code at the workspace `.venv` created by `uv sync --all-extras --dev --frozen`, and `python.analysis.extraPaths` includes `src` so Pylance resolves the src-layout `notewise` package and test dependencies.

`css.validate` and `scss.validate` are disabled because the website CSS uses Tailwind v4 directives, CSS nesting, and custom properties that are validated by the website toolchain instead of VS Code's built-in validators.

Re-enable these validators if those custom directives are removed.
