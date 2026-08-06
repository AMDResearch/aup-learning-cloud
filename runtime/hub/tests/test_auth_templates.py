from itertools import product
from types import SimpleNamespace

import pytest
from auth_template_support import (
    LOGIN_NEXT_CASES,
    TEMPLATES,
    HtmlProbe,
    base_context,
    loaded_auth_modules,
    probe_html,
    template_environment,
)
from tornado.escape import url_escape

VALID_VARIANTS = {
    "auto-login": (True, False, False, False),
    "dummy": (False, True, False, False),
    "native": (False, False, True, False),
    "github": (False, False, False, True),
    "native-github": (False, False, True, True),
}
INVALID_VARIANTS = tuple(values for values in product((False, True), repeat=4) if values not in VALID_VARIANTS.values())


def projected_context(monkeypatch: pytest.MonkeyPatch, providers: tuple[bool, bool, bool, bool]) -> dict[str, object]:
    with loaded_auth_modules(monkeypatch) as modules:
        auth = modules.config.AuthCapabilities(*providers)
        return dict(modules.setup._build_auth_template_vars(auth))


@pytest.mark.parametrize(("variant", "providers"), VALID_VARIANTS.items())
def test_setup_projects_explicit_auth_template_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    providers: tuple[bool, bool, bool, bool],
) -> None:
    context = projected_context(monkeypatch, providers)

    assert context == {
        "auth_auto_login": variant == "auto-login",
        "auth_dummy": variant == "dummy",
        "auth_native": variant in {"native", "native-github"},
        "auth_github": variant in {"github", "native-github"},
        "password_management_enabled": variant in {"native", "native-github"},
        "hide_logout": variant == "auto-login",
    }


@pytest.mark.parametrize("providers", INVALID_VARIANTS)
def test_invalid_auth_capabilities_are_rejected_before_render(
    monkeypatch: pytest.MonkeyPatch,
    providers: tuple[bool, bool, bool, bool],
) -> None:
    with loaded_auth_modules(monkeypatch) as modules:
        auth = modules.config.AuthCapabilities(*providers)
        rendered = False

        with pytest.raises(modules.config.AuthConfigurationError):
            context = modules.setup._build_auth_template_vars(auth)
            template_environment().get_template("login.html").render(**base_context(), **context)
            rendered = True

        assert rendered is False


def test_auth_templates_do_not_branch_on_legacy_mode_names() -> None:
    for name in ("login.html", "page.html", "change-password.html", "admin-reset-password.html"):
        source = (TEMPLATES / name).read_text(encoding="utf-8")
        assert "authenticator_mode" not in source
        assert "auth_mode" not in source


@pytest.mark.parametrize(("variant", "providers"), VALID_VARIANTS.items())
def test_login_renders_enabled_authentication_controls(
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    providers: tuple[bool, bool, bool, bool],
) -> None:
    context = base_context() | projected_context(monkeypatch, providers)
    if variant == "github":
        context |= {"login_service": "GitHub", "login_github_helper_text": "Use your approved GitHub account."}
    probe = probe_html(template_environment().get_template("login.html").render(**context))
    form_actions = {form.get("action") for form in probe.forms}
    input_names = {field.get("name") for field in probe.inputs}
    password_toggles = [button for button in probe.buttons if "password-toggle" in (button.get("class") or "").split()]
    visible_text = " ".join(probe.text)

    assert ("username" in input_names and "password" in input_names) is (
        variant in {"dummy", "native", "native-github"}
    )
    assert len(password_toggles) == (1 if variant in {"dummy", "native", "native-github"} else 0)
    assert all(button.get("aria-label") == "Show password" for button in password_toggles)
    if variant == "dummy":
        assert "Development Mode - Any username/password accepted" in visible_text
    else:
        assert "Development Mode" not in visible_text
    assert ("/hub/login?next=/hub/home" in form_actions) is (variant in {"dummy", "native"})
    assert probe.hrefs.count("/hub/oauth_login?next=/hub/home") == (2 if variant == "github" else 0)
    assert ("/hub/github/oauth_login?next=/hub/home" in probe.hrefs) is (variant == "native-github")
    assert ("/hub/native/login?next=/hub/home" in form_actions) is (variant == "native-github")
    assert "auplc-powered-by-footer" in probe.ids
    if variant in {"dummy", "native", "native-github"}:
        assert any(field.get("name") == "_xsrf" and field.get("value") == "csrf-token" for field in probe.inputs)


def _field_by_name(probe: HtmlProbe, name: str) -> dict[str, str | None]:
    return next(field for field in probe.inputs if field.get("name") == name)


def _classes(attributes: dict[str, str | None]) -> set[str]:
    return set((attributes.get("class") or "").split())


def test_native_login_controls_share_the_rendered_dom_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    native_context = base_context() | projected_context(monkeypatch, VALID_VARIANTS["native"])
    composed_context = base_context() | projected_context(monkeypatch, VALID_VARIANTS["native-github"])

    native = probe_html(template_environment().get_template("login.html").render(**native_context))
    composed = probe_html(template_environment().get_template("login.html").render(**composed_context))

    for field_name in ("username", "password"):
        native_field = _field_by_name(native, field_name)
        composed_field = _field_by_name(composed, field_name)
        assert _classes(native_field) == _classes(composed_field)
        assert "login-input" in _classes(native_field)
        assert "required" in native_field
        assert "required" in composed_field
        assert native_field.get("autocomplete") == composed_field.get("autocomplete")
    assert {label.get("for") for label in native.labels} == {"username_input", "password_input"}
    assert {label.get("for") for label in composed.labels} == {"username_input", "password_input"}
    assert _field_by_name(native, "username").get("value") == _field_by_name(composed, "username").get("value")
    assert "autofocus" in _field_by_name(native, "username")
    assert "autofocus" in _field_by_name(composed, "username")


def test_composed_login_renders_one_ordered_card_without_nested_options(monkeypatch: pytest.MonkeyPatch) -> None:
    context = base_context() | projected_context(monkeypatch, VALID_VARIANTS["native-github"])
    context["login_github_helper_text"] = "Use your approved GitHub account."

    probe = probe_html(template_environment().get_template("login.html").render(**context))

    assert sum("login-card" in _classes(div) for div in probe.divs) == 1
    assert all("login-option" not in _classes(div) for div in probe.divs)
    assert sum("login-divider" in _classes(div) for div in probe.divs) == 1
    assert probe.github_button_icon_count == 1
    visible_text = " ".join(probe.text)
    assert "Or use local account" in visible_text
    assert "Use your approved GitHub account." in visible_text
    assert "Username" in visible_text
    assert "Password" in visible_text
    assert "Login" in visible_text

    github_offset = next(
        index
        for index, (event, tag, attributes) in enumerate(probe.events)
        if event == "start" and tag == "a" and attributes is not None and "login-github-button" in _classes(attributes)
    )
    divider_offset = next(
        index
        for index, (event, tag, attributes) in enumerate(probe.events)
        if event == "start" and tag == "div" and attributes is not None and "login-divider" in _classes(attributes)
    )
    form_offset = next(
        index for index, (event, tag, _attributes) in enumerate(probe.events) if event == "start" and tag == "form"
    )
    assert github_offset < divider_offset < form_offset


@pytest.mark.parametrize(
    ("raw_next", "template_next", "form_next"),
    LOGIN_NEXT_CASES,
)
def test_direct_login_routes_preserve_their_existing_template_behavior(
    raw_next: str, template_next: str, form_next: str
) -> None:
    environment = template_environment()
    assert url_escape(raw_next) == template_next

    native = probe_html(
        environment.get_template("login.html").render(**(base_context() | {"auth_native": True, "next": template_next}))
    )
    github = probe_html(
        environment.get_template("login.html").render(**(base_context() | {"auth_github": True, "next": template_next}))
    )

    github_button = next(anchor for anchor in github.anchors if "login-github-button" in _classes(anchor))
    assert [form.get("action") for form in native.forms] == [f"/hub/login?next={form_next}"]
    assert github_button.get("href") == f"/hub/oauth_login?next={template_next}"


@pytest.mark.parametrize(
    ("template_next", "form_next"),
    [(template_next, form_next) for _raw_next, template_next, form_next in LOGIN_NEXT_CASES],
)
def test_composed_login_routes_preserve_multi_authenticator_next_behavior(template_next: str, form_next: str) -> None:
    composed = probe_html(
        template_environment()
        .get_template("login.html")
        .render(**(base_context() | {"auth_native": True, "auth_github": True, "next": template_next}))
    )

    github_button = next(anchor for anchor in composed.anchors if "login-github-button" in _classes(anchor))
    expected_suffix = f"?next={template_next}" if template_next else ""
    expected_form_suffix = f"?next={form_next}" if template_next else ""
    assert github_button.get("href") == f"/hub/github/oauth_login{expected_suffix}"
    assert [form.get("action") for form in composed.forms] == [f"/hub/native/login{expected_form_suffix}"]


def test_login_omits_darkmode_script_while_normal_pages_keep_it() -> None:
    environment = template_environment()

    login = probe_html(environment.get_template("login.html").render(**base_context()))
    page = probe_html(environment.get_template("page.html").render(**base_context()))

    assert "/hub/static/js/darkmode.js" not in {script.get("src") for script in login.scripts}
    assert "/hub/static/js/darkmode.js" in {script.get("src") for script in page.scripts}


def test_login_uses_theme_initializer_without_a_toggle_dependency() -> None:
    html = template_environment().get_template("login.html").render(**base_context())
    probe = probe_html(html)

    assert any(script.get("id") == "login-theme-init" for script in probe.scripts)
    assert "dark-theme-toggle" not in html


@pytest.mark.parametrize(("variant", "providers"), VALID_VARIANTS.items())
def test_page_controls_follow_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    providers: tuple[bool, bool, bool, bool],
) -> None:
    context = base_context() | projected_context(monkeypatch, providers)
    context["user"] = SimpleNamespace(
        name="learner",
        json_escaped_name="learner",
        spawner=SimpleNamespace(options_form=False),
    )

    html = template_environment().get_template("page.html").render(**context)
    probe = probe_html(html)

    assert ("logout" in probe.ids) is (variant != "auto-login")
    assert ("change-password" in probe.ids) is (variant in {"native", "native-github"})
    assert ("auth/check-force-password-change" in html) is (variant in {"native", "native-github"})


@pytest.mark.parametrize(("variant", "providers"), VALID_VARIANTS.items())
def test_anonymous_login_link_follows_auto_login_capability(
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    providers: tuple[bool, bool, bool, bool],
) -> None:
    context = base_context() | projected_context(monkeypatch, providers)

    probe = probe_html(template_environment().get_template("page.html").render(**context))

    assert ("login" in probe.ids) is (variant != "auto-login")


def test_composed_github_user_has_no_native_password_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    context = base_context() | projected_context(monkeypatch, VALID_VARIANTS["native-github"])
    context["user"] = SimpleNamespace(
        name="github:octo",
        json_escaped_name="github:octo",
        spawner=SimpleNamespace(options_form=False),
    )

    html = template_environment().get_template("page.html").render(**context)
    probe = probe_html(html)

    assert "logout" in probe.ids
    assert "change-password" not in probe.ids
    assert "auth/check-force-password-change" not in html


@pytest.mark.parametrize("template_name", ("change-password.html", "admin-reset-password.html"))
@pytest.mark.parametrize("variant", tuple(VALID_VARIANTS))
def test_password_templates_render_controls_only_for_native_capability(
    monkeypatch: pytest.MonkeyPatch,
    template_name: str,
    variant: str,
) -> None:
    context = base_context() | projected_context(monkeypatch, VALID_VARIANTS[variant])
    context |= {
        "error": "",
        "error_message": "",
        "forced_change": False,
        "password_changed": False,
        "success": False,
        "target_user": "learner",
    }

    probe = probe_html(template_environment().get_template(template_name).render(**context))

    assert bool(probe.forms) is (variant in {"native", "native-github"})


def test_attribution_footer_is_after_all_template_blocks_and_renders() -> None:
    source = (TEMPLATES / "page.html").read_text(encoding="utf-8")
    footer_offset = source.index('<footer id="auplc-powered-by-footer">')

    assert footer_offset > source.rfind("{% endblock")
    assert (
        "auplc-powered-by-footer"
        in probe_html(template_environment().get_template("page.html").render(**base_context())).ids
    )


def test_composed_login_template_does_not_delegate_markup_to_authenticator_python() -> None:
    source = (TEMPLATES / "login.html").read_text(encoding="utf-8")

    assert "custom_html" not in source
    assert "_authenticators" not in source
