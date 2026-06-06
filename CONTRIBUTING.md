# Contributing to Core of Potato

First off, thank you for considering contributing to Core of Potato! It's people like you that make Core of Potato such a great tool.

## How to Contribute

### Reporting Bugs

- Ensure the bug was not already reported by searching on GitHub under Issues.
- If you're unable to find an open issue addressing the problem, open a new one. Be sure to include a title and clear description, as much relevant information as possible, and a code sample or an executable test case demonstrating the expected behavior that is not occurring.

### Suggesting Enhancements

- Open a new issue with a clear title and description.
- Explain why this enhancement would be useful to most Core of Potato users.

### Pull Requests

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes.
5. Make sure your code lints (we use `ruff`).
6. Issue that pull request!

## Development Setup

See `requirements-dev.txt` for development dependencies. We recommend using a virtual environment.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Running Tests

We use `pytest`.
```bash
pytest
```

### Linting

We use `ruff` for linting and formatting.
```bash
ruff check .
ruff format .
```
