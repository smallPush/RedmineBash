# Repository Guidelines

## Project Structure & Module Organization

RedmineBash is a Python 3.10+ CLI with no external dependencies. `tasks` is the primary executable; `tareas` preserves compatibility. `redmine_tasks/` contains configuration loading (`config.py`), HTTP requests and pagination (`client.py`), and commands and display (`cli.py`). `tests/` contains unittest tests with simulated responses. `README.md` documents setup and usage. No web frontend or static assets are required.

## Build, Test, and Development Commands

Run `./tasks --help` or `make help` for usage, `./tasks` or `make tasks` for your open issues, and `make test` for the test suite. Without Make, use `python3 -m unittest discover -s tests -v`. There is no build step or dependency installation. `./tasks check` verifies the real connection; write commands support `--dry-run`.

## Coding Style & Naming Conventions

Use four spaces, standard Python conventions, descriptive snake_case names, and small modules. Follow existing code; no formatter or linter is configured. Keep formatting-only changes separate from functional changes.

## Testing Guidelines

Use `unittest`, with `test_*.py` files and `test_*` methods. Mock Redmine responses; tests must not require credentials or mutate real issues. Cover request payloads, pagination, configuration, errors, and CLI compatibility. No coverage threshold is defined.

## Commit & Pull Request Guidelines

Use concise, imperative English subjects, such as `Add deployment configuration`, and keep commits focused.

Pull requests should explain the change, link relevant issues, and describe validation performed. Include screenshots for visual changes and identify configuration or deployment steps when applicable.

## Redmine Comment Language

Write and review comments on Redmine issues in Catalan. Apply this rule to suggested drafts and comments submitted through the CLI. Preserve code, commands, URLs, and technical identifiers in their original form.

## Project Language Conventions

Write user-facing help, usage documentation, output labels, and diagnostics in Catalan. Use English for code identifiers, comments, docstrings, command and option names, Make targets, and machine-readable JSON keys and result values. Preserve server-provided content. Keep legacy Spanish commands as compatibility aliases; document the English interface for new usage.

## Security & Configuration

Never commit credentials, private keys, or populated secret files. Treat `.aws/` as sensitive local configuration. Provide placeholder configuration examples and document required secrets without exposing their values.
