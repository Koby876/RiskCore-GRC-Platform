# Contributing to RiskCore

Thank you for your interest in contributing.

## Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Run the test suite (if applicable)
5. Submit a pull request

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/riskcore.git
cd riskcore
pip install -r requirements.txt
python main.py
```

## Code Style

- Follow existing patterns in the codebase
- PySide6 UI code: widgets in `ui/`, reusable components in `widgets/`
- All DB access through `core/database/db.py`
- Design tokens (colours, fonts, spacing) from `assets/themes/design_system.py`
- Background operations on `QThread` — never block the main thread

## What Not to Commit

See `.gitignore` — user data files (`riskcore.db`, keys, logs) must never be committed.

## Pull Request Guidelines

- One feature or fix per PR
- Include a clear description of what changed and why
- Do not break existing functionality
- Test with at least one risk and one treatment in the database
