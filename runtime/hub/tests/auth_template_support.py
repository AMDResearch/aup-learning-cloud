import importlib.util
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "frontend" / "templates"
FIRSTUSE = ROOT / "core" / "authenticators" / "firstuse.py"
MULTI = ROOT / "core" / "authenticators" / "multi.py"
LOGIN_NEXT_CASES = (
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


class HtmlProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.anchors: list[dict[str, str | None]] = []
        self.divs: list[dict[str, str | None]] = []
        self.forms: list[dict[str, str | None]] = []
        self.inputs: list[dict[str, str | None]] = []
        self.labels: list[dict[str, str | None]] = []
        self.buttons: list[dict[str, str | None]] = []
        self.scripts: list[dict[str, str | None]] = []
        self.events: list[tuple[str, str, dict[str, str | None] | None]] = []
        self.github_button_icon_count = 0
        self._inside_github_button = False
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self.events.append(("start", tag, attributes))
        if element_id := attributes.get("id"):
            self.ids.add(element_id)
        if tag == "a" and (href := attributes.get("href")):
            self.hrefs.append(href)
            self.anchors.append(attributes)
            self._inside_github_button = "login-github-button" in (attributes.get("class") or "").split()
        if tag == "div":
            self.divs.append(attributes)
        if tag == "form":
            self.forms.append(attributes)
        if tag == "input":
            self.inputs.append(attributes)
        if tag == "label":
            self.labels.append(attributes)
        if tag == "button":
            self.buttons.append(attributes)
        if tag == "script":
            self.scripts.append(attributes)
        if tag == "svg" and self._inside_github_button:
            self.github_button_icon_count += 1

    def handle_endtag(self, tag: str) -> None:
        self.events.append(("end", tag, None))
        if tag == "a":
            self._inside_github_button = False

    def handle_data(self, data: str) -> None:
        if text := " ".join(data.split()):
            self.text.append(text)
            self.events.append(("text", text, None))


def template_environment() -> Environment:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=True,
        undefined=StrictUndefined,
    )
    environment.globals["static_url"] = lambda value, **_kwargs: f"/hub/static/{value}"
    return environment


def base_context() -> dict[str, object]:
    return {
        "admin_access": False,
        "announcement": "",
        "authenticator_login_url": "/hub/oauth_login?next=/hub/home",
        "base_url": "/hub/",
        "custom_html": "",
        "login_github_helper_text": "",
        "login_error": "",
        "login_service": "",
        "login_url": "/hub/login",
        "logo_url": "",
        "logout_url": "/hub/logout",
        "next": "/hub/home",
        "no_spawner_check": True,
        "parsed_scopes": [],
        "platform_name": "AUP Learning Cloud",
        "powered_by": "AUP Learning Cloud",
        "prefix": "/hub/",
        "services": [],
        "user": None,
        "username": "",
        "version_hash": "",
        "xsrf": "csrf-token",
        "xsrf_token": "csrf-token",
        "auth_auto_login": False,
        "auth_dummy": False,
        "auth_native": False,
        "auth_github": False,
        "password_management_enabled": False,
        "hide_logout": False,
    }


def probe_html(html: str) -> HtmlProbe:
    probe = HtmlProbe()
    probe.feed(html)
    return probe


@contextmanager
def loaded_multi_authenticator(monkeypatch: pytest.MonkeyPatch) -> Iterator[types.SimpleNamespace]:
    with monkeypatch.context() as module_patch:
        core = types.ModuleType("core")
        core.__path__ = [str(ROOT / "core")]
        authenticators = types.ModuleType("core.authenticators")
        authenticators.__path__ = [str(ROOT / "core" / "authenticators")]
        core.authenticators = authenticators
        module_patch.setitem(sys.modules, "core", core)
        module_patch.setitem(sys.modules, "core.authenticators", authenticators)

        bcrypt = types.ModuleType("bcrypt")
        firstuseauthenticator = types.ModuleType("firstuseauthenticator")

        class FirstUseAuthenticator:
            def login_url(self, base_url: str) -> str:
                return f"{base_url}native/login"

        firstuseauthenticator.FirstUseAuthenticator = FirstUseAuthenticator
        models = types.ModuleType("core.authenticators.models")
        models.UserPassword = type("UserPassword", (), {})
        database = types.ModuleType("core.database")
        database.get_session = lambda: None
        database.session_scope = lambda: None
        for module in (bcrypt, firstuseauthenticator, models, database):
            module_patch.setitem(sys.modules, module.__name__, module)

        firstuse_spec = importlib.util.spec_from_file_location("core.authenticators.firstuse", FIRSTUSE)
        assert firstuse_spec is not None and firstuse_spec.loader is not None
        firstuse = importlib.util.module_from_spec(firstuse_spec)
        module_patch.setitem(sys.modules, "core.authenticators.firstuse", firstuse)
        firstuse_spec.loader.exec_module(firstuse)

        multiauthenticator = types.ModuleType("multiauthenticator")

        class MultiAuthenticator:
            def __init__(self) -> None:
                self._authenticators = []

        multiauthenticator.MultiAuthenticator = MultiAuthenticator
        multiauthenticator_module = types.ModuleType("multiauthenticator.multiauthenticator")
        multiauthenticator_module.PREFIX_SEPARATOR = ":"
        module_patch.setitem(sys.modules, "multiauthenticator", multiauthenticator)
        module_patch.setitem(sys.modules, "multiauthenticator.multiauthenticator", multiauthenticator_module)

        multi_spec = importlib.util.spec_from_file_location("core.authenticators.multi", MULTI)
        assert multi_spec is not None and multi_spec.loader is not None
        multi = importlib.util.module_from_spec(multi_spec)
        module_patch.setitem(sys.modules, "core.authenticators.multi", multi)
        multi_spec.loader.exec_module(multi)

        class ExternalAuthenticator:
            service_name = "GitHub"
            login_service = "GitHub"
            username_prefix = ""

            def login_url(self, base_url: str) -> str:
                return f"{base_url}github/oauth_login"

        yield types.SimpleNamespace(
            multi=multi.CustomMultiAuthenticator(),
            native=firstuse.CustomFirstUseAuthenticator(),
            external=ExternalAuthenticator(),
        )


@contextmanager
def loaded_auth_modules(monkeypatch: pytest.MonkeyPatch) -> Iterator[types.SimpleNamespace]:
    with monkeypatch.context() as module_patch:
        bcrypt = types.ModuleType("bcrypt")
        module_patch.setitem(sys.modules, "bcrypt", bcrypt)

        config_name = "task9_auth_config"
        config_spec = importlib.util.spec_from_file_location(config_name, ROOT / "core" / "config.py")
        assert config_spec is not None and config_spec.loader is not None
        config = importlib.util.module_from_spec(config_spec)
        module_patch.setitem(sys.modules, config_name, config)
        config_spec.loader.exec_module(config)

        setup_name = "task9_auth_setup"
        setup_spec = importlib.util.spec_from_file_location(setup_name, ROOT / "core" / "setup.py")
        assert setup_spec is not None and setup_spec.loader is not None
        setup = importlib.util.module_from_spec(setup_spec)
        module_patch.setitem(sys.modules, setup_name, setup)
        setup_spec.loader.exec_module(setup)

        yield types.SimpleNamespace(config=config, setup=setup)
