import importlib.util
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template
from tornado.escape import url_escape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "frontend" / "templates"
FIRSTUSE = ROOT / "core" / "authenticators" / "firstuse.py"
MULTI = ROOT / "core" / "authenticators" / "multi.py"


class HtmlProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.anchors: list[dict[str, str | None]] = []
        self.forms: list[dict[str, str | None]] = []
        self.inputs: list[dict[str, str | None]] = []
        self.buttons: list[dict[str, str | None]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if element_id := attributes.get("id"):
            self.ids.add(element_id)
        if tag == "a" and (href := attributes.get("href")):
            self.hrefs.append(href)
            self.anchors.append(attributes)
        if tag == "form":
            self.forms.append(attributes)
        if tag == "input":
            self.inputs.append(attributes)
        if tag == "button":
            self.buttons.append(attributes)

    def handle_data(self, data: str) -> None:
        if text := " ".join(data.split()):
            self.text.append(text)


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
        "github_helper_text": "",
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


def render_multi_html(state: types.SimpleNamespace, next_value: str) -> str:
    return Template(state.multi.get_custom_html("/hub/")).render(xsrf="csrf-token", next=url_escape(next_value))


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
