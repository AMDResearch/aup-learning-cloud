# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'AUP Learning Cloud'
copyright = '2025-2026, Advanced Micro Devices, Inc. All rights reserved'
author = 'AMD Research'

version = 'v0.3'
release = 'v0.3'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'myst_parser',
    'sphinx_copybutton',
    'sphinx_design',
]

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_book_theme'
html_static_path = ['_static']

# MyST parser settings
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "tasklist",
]

# Copy button settings
copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: | {2,5}\.\.\.: | {5,8}: "
copybutton_prompt_is_regexp = True

# Sphinx Book Theme options (see sphinx-book-theme docs for more)
html_theme_options = {
    "repository_url": "",
    "use_repository_button": False,
    "navigation_with_keys": True,
    "show_navbar_depth": 1,
}
# For AMD brand colors (#E8175D), add _static/custom.css and set html_css_files = ["custom.css"]

# Project logo (optional - you can add AMD logo later)
# html_logo = "_static/logo.png"

# Source file suffix
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}
