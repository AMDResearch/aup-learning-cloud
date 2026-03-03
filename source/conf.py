# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'AUP Learning Cloud'
copyright = '2025, Advanced Micro Devices, Inc. All rights reserved'
author = 'AMD Research'

version = 'v1.0'
release = 'v1.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'myst_parser',
    'sphinx_copybutton',
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

# Furo theme options
html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#E8175D",  # AMD red
        "color-brand-content": "#E8175D",
    },
    "dark_css_variables": {
        "color-brand-primary": "#E8175D",
        "color-brand-content": "#E8175D",
    },
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
}

# Project logo (optional - you can add AMD logo later)
# html_logo = "_static/logo.png"

# Source file suffix
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}
