# Contributing to AUP Learning Cloud

Thank you for your interest in contributing to AUP Learning Cloud! This document provides guidelines and setup instructions for developers.

## Development Setup

### Prerequisites

- **Python**: 3.10+
- **Node.js**: 20+
- **pnpm**: 9+
- **Git**: 2.30+

### Initial Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/AMDResearch/aup-learning-cloud-dev.git
   cd aup-learning-cloud-dev
   ```

2. **Install Python dependencies**
   ```bash
   pip install ruff pre-commit yamllint
   ```

3. **Install frontend dependencies**
   ```bash
   cd runtime/admin/frontend/admin-frontend
   pnpm install
   cd -
   ```

4. **Install pre-commit hooks** (optional but recommended)
   ```bash
   pre-commit install
   ```
   This will automatically run lint checks before each commit.

### Code Quality Tools

We use the following tools to maintain code quality:

#### Python (Ruff)
- **Linter**: Checks code style and potential bugs
- **Formatter**: Auto-formats code to match project style
- **Config**: `pyproject.toml`

Run checks:
```bash
# Lint check
ruff check .

# Format check
ruff format --check .

# Auto-fix issues
ruff check --fix .
ruff format .
```

#### Frontend (ESLint + Prettier)
- **ESLint**: JavaScript/TypeScript/Vue linter
- **Prettier**: Code formatter
- **TypeScript**: Type checking
- **Config**: `runtime/admin/frontend/admin-frontend/eslint.config.js`, `.prettierrc`

Run checks:
```bash
cd runtime/admin/frontend/admin-frontend

# Lint
pnpm run lint

# Format check
pnpm run format:check

# Type check
pnpm run type-check

# Auto-fix
pnpm run lint:fix
pnpm run format
```

#### YAML (yamllint)
- **Config**: `.yamllint.yaml`

Run checks:
```bash
yamllint .
```

#### Shell (ShellCheck)
- **Config**: `.shellcheckrc`

Run checks:
```bash
# Install on Ubuntu/Debian
sudo apt-get install shellcheck

# Run
find . -name "*.sh" -o -name "*.bash" | \
  grep -v node_modules | \
  grep -v .git | \
  xargs -r shellcheck
```

### Editor Configuration

#### VSCode (Recommended)
1. Install recommended extensions (prompt will appear automatically):
   - Ruff
   - Python
   - Prettier
   - ESLint
   - Vue - Official (Volar)
   - YAML
   - ShellCheck
   - EditorConfig
   - GitLens

2. Settings are pre-configured in `.vscode/settings.json`:
   - Format on save enabled
   - Auto-organize imports
   - Use project-specific formatters

#### Other Editors
- EditorConfig configuration: `.editorconfig`
- Use plugins for Ruff, ESLint, and Prettier in your editor

### Before Submitting a PR

1. **Run all lint checks locally**:
   ```bash
   # Python
   ruff check .
   ruff format --check .

   # YAML
   yamllint .

   # Frontend (from runtime/admin/frontend/admin-frontend)
   pnpm run lint
   pnpm run format:check
   pnpm run type-check
   ```

2. **Ensure all checks pass**:
   - CI will automatically run these checks on your PR
   - PRs with failing lint checks cannot be merged

3. **Commit message format**:
   - Use clear, descriptive commit messages
   - Start with a verb (Add, Fix, Update, Refactor, etc.)
   - Keep the first line under 72 characters

### Jupyter Notebooks

Teaching notebooks in `projects/` have relaxed lint rules:
- Imports don't need to be at the top
- `import *` is allowed for teaching purposes
- Single-letter variables (e.g., `x`, `y`, `l`) are permitted
- Unused variables are allowed (exploratory code)
- Lambda assignments are acceptable (teaching patterns)

Standard production code rules apply to:
- `runtime/jupyterhub/files/hub/jupyterhub_config.py`
- `scripts/`
- All other Python files

### Line Endings

- **All files use LF (Unix-style) line endings**
- **All files must end with a newline**
- Git is configured to automatically normalize line endings (`.gitattributes`)
- If you're on Windows, configure Git:
  ```bash
  git config --global core.autocrlf input
  ```

## Branch Naming Example
| Prefix | Use Case | Example |
| :--- | :--- | :--- |
| **feature/** | Developing new features or enhancements | `feature/user-login` |
| **bugfix/** | Fixing bugs in development or staging | `bugfix/sidebar-display` |
| **hotfix/** | Urgent fixes for critical issues in Production | `hotfix/payment-gateway-crash` |
| **refactor/** | Code restructuring without changing functionality | `refactor/api-response-handler` |
| **docs/** | Documentation updates only | `docs/update-readme` |
| **chore/** | Routine tasks, dependency updates, build config | `chore/update-dependencies` |
| **test/** | Adding or correcting test cases | `test/add-unit-tests` |
| **perf/** | Performance optimizations | `perf/database-query-tuning` |
| **style/** | Code formatting, linting (no logic change) | `style/fix-lint-errors` |
| **ci/** | CI/CD configuration and scripts | `ci/github-actions-setup` |

## Questions?

- Open an issue for bugs or feature requests
- Check existing documentation in the `source/` directory (this documentation site)

Thank you for contributing!
