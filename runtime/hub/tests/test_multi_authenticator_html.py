import pytest
from auth_template_support import loaded_multi_authenticator, probe_html, render_multi_html

NEXT_CASES = (
    (
        "/hub/spawn?x=1&y=two words",
        "%2Fhub%2Fspawn%3Fx%3D1%26y%3Dtwo+words",
        "%252Fhub%252Fspawn%253Fx%253D1%2526y%253Dtwo%2Bwords",
    ),
    (
        "/路径?值=你好 世界",
        "%2F%E8%B7%AF%E5%BE%84%3F%E5%80%BC%3D%E4%BD%A0%E5%A5%BD+%E4%B8%96%E7%95%8C",
        "%252F%25E8%25B7%25AF%25E5%25BE%2584%253F%25E5%2580%25BC%253D%25E4%25BD%25A0%25E5%25A5%25BD%2B%25E4%25B8%2596%25E7%2595%258C",
    ),
    ("", "", ""),
)


@pytest.mark.parametrize(("next_value", "escaped_next", "form_next"), NEXT_CASES)
def test_native_child_renders_inline_form_with_encoded_next(
    monkeypatch: pytest.MonkeyPatch,
    next_value: str,
    escaped_next: str,
    form_next: str,
) -> None:
    with loaded_multi_authenticator(monkeypatch) as state:
        state.multi._authenticators = [state.native]
        probe = probe_html(render_multi_html(state, next_value))

    expected_action = "/hub/native/login" + (f"?next={form_next}" if escaped_next else "")
    assert [form.get("action") for form in probe.forms] == [expected_action]
    fields = {field.get("name"): field for field in probe.inputs}
    assert fields["_xsrf"].get("value") == "csrf-token"
    assert fields["username"].get("placeholder") == "Username"
    assert fields["username"].get("aria-label") == "Username"
    assert "required" in fields["username"]
    assert fields["password"].get("placeholder") == "Password"
    assert fields["password"].get("aria-label") == "Password"
    assert "required" in fields["password"]
    assert "login-submit" in (probe.buttons[0].get("class") or "").split()


@pytest.mark.parametrize(("next_value", "escaped_next", "form_next"), NEXT_CASES)
def test_external_child_renders_encoded_link_even_with_empty_prefix(
    monkeypatch: pytest.MonkeyPatch,
    next_value: str,
    escaped_next: str,
    form_next: str,
) -> None:
    with loaded_multi_authenticator(monkeypatch) as state:
        state.multi._authenticators = [state.external]
        probe = probe_html(render_multi_html(state, next_value))

    expected_href = "/hub/github/oauth_login" + (f"?next={escaped_next}" if form_next else "")
    assert probe.hrefs == [expected_href]
    assert probe.forms == []
    classes = (probe.anchors[0].get("class") or "").split()
    assert "login-github-button" in classes
    assert "text-white" not in classes
