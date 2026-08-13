from pathlib import Path
from typing import Final

TEMPLATES: Final = Path(__file__).resolve().parents[1] / "frontend" / "templates"


def test_login_split_layout_starts_at_large_breakpoint() -> None:
    source = (TEMPLATES / "login.html").read_text(encoding="utf-8")

    assert 'class="min-h-screen flex flex-col lg:flex-row"' in source
    assert 'class="w-full lg:w-2/5 bg-black flex flex-col justify-center items-center p-10 lg:p-16"' in source
    assert 'class="login-main-panel w-full lg:w-3/5 flex items-center justify-center p-6 lg:p-16"' in source
    assert all(token not in source for token in ("md:flex-row", "md:w-2/5", "md:w-3/5", "md:p-16"))


def test_attribution_footer_uses_accessible_padded_wrapping_styles() -> None:
    source = (TEMPLATES / "page.html").read_text(encoding="utf-8")
    footer_rule = source.split("#auplc-powered-by-footer {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    link_selector = "#auplc-powered-by-footer a {"

    assert "opacity:" not in footer_rule
    assert "padding: 6px var(--bs-gutter-x, 0.75rem);" in footer_rule
    assert "color: var(--bs-secondary-color);" in footer_rule
    assert "overflow-wrap: anywhere;" in footer_rule
    assert link_selector in source
    link_rule = source.split(link_selector, maxsplit=1)[1].split("}", maxsplit=1)[0]
    assert "color: var(--bs-link-color);" in link_rule
