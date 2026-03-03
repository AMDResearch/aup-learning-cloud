# AUP Learning Cloud Documentation

This branch contains the Sphinx-based documentation for AUP Learning Cloud.

## Building Documentation Locally

### Prerequisites

```bash
pip install -r requirements.txt
```

### Build HTML Documentation

```bash
make html
```

The built documentation will be in `build/html/`. Open `build/html/index.html` in your browser.

### Other Build Options

```bash
# Clean build directory
make clean

# Build and watch for changes (auto-rebuild)
sphinx-autobuild source build/html
```

## Documentation Structure

```
source/
├── index.rst                    # Main documentation index
├── conf.py                      # Sphinx configuration
├── introduction/                # Introduction
│   └── overview.md
├── installation/                # Installation guides
│   ├── quick-start.md
│   ├── single-node.md
│   └── multi-node.md
├── jupyterhub/                  # JupyterHub configuration
│   ├── index.md
│   ├── README.md
│   ├── configuration-reference.md
│   ├── authentication-guide.md
│   ├── user-management.md
│   ├── quota-system.md
│   └── github-oauth-setup.md
├── user-guide/                  # User guides
│   ├── index.md
│   └── admin-manual.md
├── contributing/                # Contributing guide
│   ├── index.md
│   └── contributing.md
└── _static/                     # Static files (images, CSS, etc.)
    └── images/
```

## GitHub Pages Deployment

Documentation is automatically built and deployed to GitHub Pages when changes are pushed to the `docs` branch.

The workflow is defined in `.github/workflows/docs.yml`.

## Contributing to Documentation

1. Edit Markdown files in `source/` directories
2. Add images to `source/_static/images/`
3. Build locally to test: `make html`
4. Commit and push changes

### Markdown Format

This documentation uses MyST Parser for Markdown support. See [MyST documentation](https://myst-parser.readthedocs.io/) for syntax details.

## Links

- [Sphinx Documentation](https://www.sphinx-doc.org/)
- [Read the Docs Theme](https://sphinx-rtd-theme.readthedocs.io/)
- [MyST Parser](https://myst-parser.readthedocs.io/)
