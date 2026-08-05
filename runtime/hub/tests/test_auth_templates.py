from itertools import product
from types import SimpleNamespace

import pytest
from auth_template_support import (
    TEMPLATES,
    base_context,
    loaded_auth_modules,
    loaded_multi_authenticator,
    probe_html,
    render_multi_html,
    template_environment,
)

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
        context |= {"login_service": "GitHub", "github_helper_text": "Use your approved GitHub account."}
    if variant == "native-github":
        with loaded_multi_authenticator(monkeypatch) as state:
            state.multi._authenticators = [state.external, state.native]
            context["custom_html"] = render_multi_html(state, str(context["next"]))

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
    assert ("/hub/github/oauth_login?next=%2Fhub%2Fhome" in probe.hrefs) is (variant == "native-github")
    assert ("/hub/native/login?next=%252Fhub%252Fhome" in form_actions) is (variant == "native-github")
    assert "auplc-powered-by-footer" in probe.ids
    if variant in {"dummy", "native", "native-github"}:
        assert any(field.get("name") == "_xsrf" and field.get("value") == "csrf-token" for field in probe.inputs)


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
