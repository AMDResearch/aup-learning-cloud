import pytest
from auth_template_support import loaded_multi_authenticator


def test_multi_authenticator_custom_html_is_intentionally_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    with loaded_multi_authenticator(monkeypatch) as state:
        state.multi._authenticators = [state.external, state.native]

        custom_html = state.multi.get_custom_html("/hub/")

    assert custom_html == ""
