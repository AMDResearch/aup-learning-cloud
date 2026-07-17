# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import asyncio
import importlib.util
import inspect
import json
import sys
import types
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

if "jupyterhub.apihandlers" not in sys.modules:
    jupyterhub_module = types.ModuleType("jupyterhub")
    apihandlers_module = types.ModuleType("jupyterhub.apihandlers")
    handlers_module = types.ModuleType("jupyterhub.handlers")
    apihandlers_module.APIHandler = type("APIHandler", (), {})
    handlers_module.BaseHandler = type("BaseHandler", (), {})
    sys.modules["jupyterhub"] = jupyterhub_module
    sys.modules["jupyterhub.apihandlers"] = apihandlers_module
    sys.modules["jupyterhub.handlers"] = handlers_module

if "multiauthenticator" not in sys.modules:
    multiauthenticator_module = types.ModuleType("multiauthenticator")
    multiauthenticator_module.MultiAuthenticator = type("MultiAuthenticator", (), {})
    sys.modules["multiauthenticator"] = multiauthenticator_module

if "core" not in sys.modules:
    core_module = types.ModuleType("core")
    core_module.__path__ = [str(CORE)]
    sys.modules["core"] = core_module

if "core.authenticators" not in sys.modules:
    auth_module = types.ModuleType("core.authenticators")
    auth_module.__path__ = [str(CORE / "authenticators")]
    auth_module.CustomFirstUseAuthenticator = type("CustomFirstUseAuthenticator", (), {})
    sys.modules["core.authenticators"] = auth_module

if "sqlalchemy" not in sys.modules:
    sqlalchemy_module = types.ModuleType("sqlalchemy")

    class _SQLAType:
        def __init__(self, *args, **kwargs):
            pass

    class _Func:
        @staticmethod
        def now():
            return None

    sqlalchemy_module.Boolean = _SQLAType
    sqlalchemy_module.DateTime = _SQLAType
    sqlalchemy_module.Integer = _SQLAType
    sqlalchemy_module.LargeBinary = _SQLAType
    sqlalchemy_module.String = _SQLAType
    sqlalchemy_module.func = _Func()
    sys.modules["sqlalchemy"] = sqlalchemy_module

if "sqlalchemy.orm" in sys.modules:
    sqlalchemy_orm_module = sys.modules["sqlalchemy.orm"]
else:
    sqlalchemy_orm_module = types.ModuleType("sqlalchemy.orm")
    sys.modules["sqlalchemy.orm"] = sqlalchemy_orm_module


class Mapped:
    def __class_getitem__(cls, _item):
        return cls


def mapped_column(*args, **kwargs):
    return None


if not hasattr(sqlalchemy_orm_module, "Mapped"):
    sqlalchemy_orm_module.Mapped = Mapped
if not hasattr(sqlalchemy_orm_module, "mapped_column"):
    sqlalchemy_orm_module.mapped_column = mapped_column
if not hasattr(sqlalchemy_orm_module, "Session"):
    sqlalchemy_orm_module.Session = type("Session", (), {})

if "core.database" not in sys.modules:
    database_module = types.ModuleType("core.database")

    class Base:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    database_module.Base = Base

    @contextmanager
    def session_scope():
        raise AssertionError("session_scope must be patched in notification tests")

    database_module.session_scope = session_scope
    sys.modules["core.database"] = database_module

if "core.quota" not in sys.modules:
    quota_module = types.ModuleType("core.quota")
    quota_module.BatchQuotaRequest = type("BatchQuotaRequest", (), {})
    quota_module.QuotaAction = type("QuotaAction", (), {})
    quota_module.QuotaModifyRequest = type("QuotaModifyRequest", (), {})
    quota_module.QuotaRefreshRequest = type("QuotaRefreshRequest", (), {})
    quota_module.get_quota_manager = lambda: None
    sys.modules["core.quota"] = quota_module

if "core.stats_handlers" not in sys.modules:
    stats_module = types.ModuleType("core.stats_handlers")
    for name in [
        "StatsActiveSSEHandler",
        "StatsDistributionHandler",
        "StatsHourlyHandler",
        "StatsMyUsageHandler",
        "StatsOverviewHandler",
        "StatsUsageHandler",
        "StatsUserHandler",
    ]:
        setattr(stats_module, name, type(name, (), {}))
    sys.modules["core.stats_handlers"] = stats_module


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


notifications = load_module("core.notifications", CORE / "notifications.py")
handlers = load_module("core.handlers", CORE / "handlers.py")

NotificationsAPIHandler = handlers.NotificationsAPIHandler
get_normalized_notifications = notifications.get_normalized_notifications


class DummyUser:
    def __init__(self, name: str):
        self.name = name


def make_handler(handler_cls, username: str = "alice"):
    handler = object.__new__(handler_cls)
    handler.current_user = DummyUser(username)
    captured = {}
    handler.set_header = lambda key, value: captured.setdefault("headers", {}).__setitem__(key, value)
    handler.finish = lambda payload: captured.setdefault("body", payload)
    return handler, captured


def test_notification_defaults_and_disabled_config_are_normalized():
    disabled_payload = get_normalized_notifications({})
    assert disabled_payload == {
        "enabled": False,
        "topbar": None,
        "homepage": {
            "enabled": False,
            "legacyAnnouncementFallback": True,
            "items": [],
        },
    }

    default_payload = get_normalized_notifications({"notifications": {"enabled": True}})
    assert default_payload["enabled"] is True
    assert default_payload["topbar"] is None
    assert default_payload["homepage"] == {
        "enabled": False,
        "legacyAnnouncementFallback": True,
        "items": [],
    }


def test_notification_severity_format_and_date_window_edge_cases():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    payload = get_normalized_notifications(
        {
            "notifications": {
                "enabled": True,
                "topbar": {
                    "enabled": True,
                    "id": "urgent-topbar",
                    "severity": "critical",
                    "format": "unsupported",
                    "title": "Top notice",
                    "message": "Attention",
                },
                "homepage": {
                    "enabled": True,
                    "items": [
                        {
                            "enabled": True,
                            "id": "future-window",
                            "title": "Future",
                            "message": "Not yet visible",
                            "startsAt": "2026-06-01T13:00:00Z",
                            "endsAt": "2026-06-01T14:00:00Z",
                        },
                        {
                            "enabled": True,
                            "id": "closed-boundary",
                            "title": "Boundary",
                            "message": "Closes exactly now",
                            "startsAt": "2026-06-01T11:00:00Z",
                            "endsAt": "2026-06-01T12:00:00Z",
                        },
                        {
                            "enabled": True,
                            "id": "invalid-window",
                            "title": "Invalid",
                            "message": "Starts after it ends",
                            "startsAt": "2026-06-01T15:00:00+02:00",
                            "endsAt": "2026-06-01T15:00:00+02:00",
                        },
                        {
                            "enabled": True,
                            "id": "active-window",
                            "title": "Active",
                            "message": "Visible now",
                            "startsAt": "2026-06-01T11:00:00",
                            "endsAt": "2026-06-01T15:00:00+02:00",
                        },
                    ],
                },
            }
        },
        now=now,
    )

    topbar = payload["topbar"]
    assert topbar["severity"] == "warning"
    assert topbar["format"] == "text"
    assert topbar["id"] == "urgent-topbar"
    assert topbar["dismissalKey"] == "urgent-topbar@1"
    assert "dismissed" not in topbar

    homepage_items = payload["homepage"]["items"]
    assert len(homepage_items) == 1
    assert homepage_items[0]["id"] == "active-window"
    assert homepage_items[0]["startsAt"] == "2026-06-01T11:00:00Z"
    assert homepage_items[0]["endsAt"] == "2026-06-01T13:00:00Z"


def test_homepage_items_default_enabled_while_topbar_stays_explicit():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    payload = get_normalized_notifications(
        {
            "notifications": {
                "enabled": True,
                "topbar": {
                    "id": "topbar-needs-enabled",
                    "title": "Hidden topbar",
                    "message": "This should not render without enabled",
                },
                "homepage": {
                    "enabled": True,
                    "items": [
                        {
                            "id": "homepage-default-active",
                            "eyebrow": "<strong>Platform</strong>",
                            "title": "Visible by default",
                            "message": "Homepage items no longer need enabled:true",
                        },
                        {
                            "enabled": False,
                            "id": "homepage-disabled",
                            "title": "Hidden",
                            "message": "This retained item stays disabled when explicitly false",
                        },
                        {
                            "id": "homepage-windowed",
                            "title": "Windowed",
                            "message": "Visible during the active window",
                            "startsAt": "2026-06-01T11:00:00Z",
                            "endsAt": "2026-06-01T13:00:00Z",
                        },
                    ],
                },
            }
        },
        now=now,
    )

    assert payload["topbar"] is None

    homepage_items = payload["homepage"]["items"]
    assert [item["id"] for item in homepage_items] == [
        "homepage-default-active",
        "homepage-windowed",
    ]
    assert homepage_items[0]["dismissalKey"] == "homepage-default-active@1"
    assert homepage_items[0]["eyebrow"] == "Platform"
    assert "eyebrowHtml" not in homepage_items[0]
    assert homepage_items[1]["startsAt"] == "2026-06-01T11:00:00Z"
    assert homepage_items[1]["endsAt"] == "2026-06-01T13:00:00Z"


def test_notification_sanitizer_allows_only_safe_rich_text():
    payload = get_normalized_notifications(
        {
            "notifications": {
                "enabled": True,
                "topbar": {
                    "enabled": True,
                    "id": "rich-notice",
                    "format": "html",
                    "severity": "info",
                    "title": (
                        "<strong>Safe</strong> "
                        '<a href="/hub/home" title="Docs">Docs</a>'
                        "<script>alert(1)</script>"
                        '<a href="javascript:alert(1)" onclick="evil()">Bad</a>'
                        '<img src="x" style="color:red">'
                    ),
                    "message": '<p style="color:red">Body</p>',
                    "link": {"label": "Go home", "url": "/hub/home"},
                },
            }
        }
    )

    topbar = payload["topbar"]
    assert topbar["severity"] == "info"
    assert topbar["format"] == "html"
    assert "<script" not in topbar["titleHtml"]
    assert "onclick" not in topbar["titleHtml"]
    assert "javascript:" not in topbar["titleHtml"]
    assert "<img" not in topbar["titleHtml"]
    assert "style=" not in topbar["titleHtml"]
    assert "<strong>Safe</strong>" in topbar["titleHtml"]
    assert 'href="/hub/home"' in topbar["titleHtml"]
    assert 'rel="noopener noreferrer"' in topbar["titleHtml"]
    assert topbar["link"] == {"label": "Go home", "url": "/hub/home", "rel": "noopener noreferrer"}
    assert "dismissed" not in topbar


def test_notifications_api_handler_is_read_only_and_has_no_user_state(monkeypatch):
    payload = {
        "enabled": True,
        "topbar": {"id": "notice", "version": "1", "dismissalKey": "notice@1"},
        "homepage": {"enabled": True, "legacyAnnouncementFallback": True, "items": []},
    }

    monkeypatch.setattr(handlers, "get_normalized_notifications", lambda: payload)

    handler, captured = make_handler(NotificationsAPIHandler, "alice")

    asyncio.run(handler.get())

    assert captured["headers"]["Content-Type"] == "application/json"
    assert json.loads(captured["body"]) == payload
    assert "dismissed" not in captured["body"]
    assert "dismissed_at" not in captured["body"]
    assert "current_user" not in inspect.getsource(NotificationsAPIHandler.get)


def test_notification_sources_have_no_dismissal_endpoint_or_model():
    source_map = {path.name: path.read_text() for path in CORE.rglob("*.py")}
    combined_source = "\n".join(source_map.values())

    assert '(r"/api/notifications", NotificationsAPIHandler)' in source_map["handlers.py"]
    assert "/api/notifications/dismiss" not in combined_source
    assert "UserNotificationDismissal" not in combined_source
    assert "notification_state" not in combined_source.lower()
