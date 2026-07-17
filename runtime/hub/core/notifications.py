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

"""Notification normalization and sanitization helpers."""

from __future__ import annotations

import html as html_lib
import logging
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

import markdown
import nh3

NotificationFormat = Literal["text", "markdown", "html"]
NotificationPayload = dict[str, Any]

ALLOWED_TAGS: frozenset[str] = frozenset({"a", "strong", "b", "em", "i", "br", "p", "ul", "ol", "li", "code"})
ALLOWED_ATTRIBUTES: dict[str, frozenset[str]] = {"a": frozenset({"href", "title", "target", "rel"})}
ALLOWED_URL_SCHEMES: frozenset[str] = frozenset({"http", "https", "mailto"})
LINK_REL = "noopener noreferrer"
SUPPORTED_FORMATS: frozenset[str] = frozenset({"text", "markdown", "html"})
SUPPORTED_SEVERITIES: frozenset[str] = frozenset({"info", "success", "warning", "danger"})

logger = logging.getLogger(__name__)

_cleaner = nh3.Cleaner(
    tags=ALLOWED_TAGS,
    attributes=ALLOWED_ATTRIBUTES,
    url_schemes=ALLOWED_URL_SCHEMES,
    link_rel=None,
)


def get_normalized_notifications(
    config: Any | None = None,
    *,
    now: datetime | None = None,
) -> NotificationPayload:
    """Return active, sanitized notifications from raw config or HubConfig."""
    raw_notifications = _resolve_notifications_config(config)
    current_time = _normalize_now(now)

    if not raw_notifications or not bool(raw_notifications.get("enabled", False)):
        return _disabled_payload()

    topbar_payload = _normalize_item(
        raw_notifications.get("topbar"),
        section="topbar",
        index=None,
        default_enabled=False,
        now=current_time,
    )

    raw_homepage = raw_notifications.get("homepage")
    homepage_enabled = isinstance(raw_homepage, Mapping) and bool(raw_homepage.get("enabled", False))
    legacy_fallback = True
    homepage_items: list[NotificationPayload] = []
    if isinstance(raw_homepage, Mapping):
        legacy_fallback = bool(raw_homepage.get("legacyAnnouncementFallback", True))
        if homepage_enabled:
            raw_items = raw_homepage.get("items") or []
            if isinstance(raw_items, list):
                for item_index, raw_item in enumerate(raw_items):
                    item_payload = _normalize_item(
                        raw_item,
                        section="homepage",
                        index=item_index,
                        default_enabled=True,
                        now=current_time,
                    )
                    if item_payload is not None:
                        homepage_items.append(item_payload)
            else:
                logger.warning("Notification homepage items must be a list; ignoring configured value")

    return {
        "enabled": True,
        "topbar": topbar_payload,
        "homepage": {
            "enabled": homepage_enabled,
            "legacyAnnouncementFallback": legacy_fallback,
            "items": homepage_items,
        },
    }


def get_active_topbar_notification(
    config: Any | None = None,
    *,
    now: datetime | None = None,
) -> NotificationPayload | None:
    """Return the active sanitized topbar notification, if configured."""
    return get_normalized_notifications(config, now=now)["topbar"]


def get_active_homepage_notifications(
    config: Any | None = None,
    *,
    now: datetime | None = None,
) -> list[NotificationPayload]:
    """Return active sanitized homepage notification items."""
    return list(get_normalized_notifications(config, now=now)["homepage"]["items"])


def sanitize_notification_content(content: Any, content_format: str = "text") -> str:
    """Render text, Markdown, or HTML into sanitized HTML."""
    raw_content = "" if content is None else str(content)
    normalized_format = _normalize_format(content_format)

    if normalized_format == "text":
        rendered_html = html_lib.escape(raw_content, quote=False).replace("\n", "<br>")
    elif normalized_format == "markdown":
        rendered_html = markdown.markdown(raw_content)
    else:
        rendered_html = raw_content

    return _add_link_rel(_cleaner.clean(rendered_html))


def _resolve_notifications_config(config: Any | None) -> Mapping[str, Any]:
    if config is None:
        from core.config import HubConfig

        return HubConfig.get().notifications
    if isinstance(config, Mapping) and isinstance(config.get("notifications"), Mapping):
        return config["notifications"]
    if hasattr(config, "notifications"):
        notifications = config.notifications
        if isinstance(notifications, Mapping):
            return notifications
        logger.warning("HubConfig notifications value must be a mapping; disabling notifications")
        return {}
    if not isinstance(config, Mapping):
        logger.warning("Notification config must be a mapping; disabling notifications")
        return {}
    return config


def _disabled_payload() -> NotificationPayload:
    return {
        "enabled": False,
        "topbar": None,
        "homepage": {
            "enabled": False,
            "legacyAnnouncementFallback": True,
            "items": [],
        },
    }


def _normalize_item(
    raw_item: Any,
    *,
    section: str,
    index: int | None,
    default_enabled: bool,
    now: datetime,
) -> NotificationPayload | None:
    item_label = section if index is None else f"{section}[{index}]"
    if not isinstance(raw_item, Mapping) or not bool(raw_item.get("enabled", default_enabled)):
        return None

    notification_id = _normalize_string(raw_item.get("id"))
    if not notification_id:
        logger.warning("Notification %s has no id; disabling item", item_label)
        return None

    if not _is_within_active_window(raw_item, item_label=item_label, now=now):
        return None

    notification_format = _normalize_format(raw_item.get("format", "text"), item_label=item_label)
    title_html = sanitize_notification_content(raw_item.get("title", ""), notification_format)
    message_html = sanitize_notification_content(raw_item.get("message", ""), notification_format)
    if not title_html.strip() and not message_html.strip():
        logger.warning("Notification %s has no title or message content; disabling item", item_label)
        return None

    version = _normalize_string(raw_item.get("version")) or "1"
    severity = _normalize_severity(raw_item.get("severity"), item_label=item_label)
    eyebrow = _normalize_plain_text(raw_item.get("eyebrow"))

    payload = {
        "id": notification_id,
        "version": version,
        "dismissalKey": f"{notification_id}@{version}",
        "severity": severity,
        "dismissible": bool(raw_item.get("dismissible", True)),
        "format": notification_format,
        "titleHtml": title_html,
        "messageHtml": message_html,
        "link": _normalize_link(raw_item.get("link"), item_label=item_label),
        "startsAt": _normalize_optional_datetime(
            raw_item.get("startsAt"), item_label=item_label, field_name="startsAt"
        ),
        "endsAt": _normalize_optional_datetime(raw_item.get("endsAt"), item_label=item_label, field_name="endsAt"),
    }
    if eyebrow:
        payload["eyebrow"] = eyebrow
    return payload


def _normalize_format(content_format: Any, *, item_label: str | None = None) -> NotificationFormat:
    normalized_format = _normalize_string(content_format).lower()
    if normalized_format in SUPPORTED_FORMATS:
        return normalized_format  # type: ignore[return-value]
    if item_label is not None:
        logger.warning(
            "Notification %s has unsupported format %r; treating content as text", item_label, content_format
        )
    return "text"


def _normalize_severity(severity: Any, *, item_label: str) -> str:
    normalized_severity = _normalize_string(severity).lower() or "warning"
    if normalized_severity in SUPPORTED_SEVERITIES:
        return normalized_severity
    logger.warning("Notification %s has unsupported severity %r; using warning", item_label, severity)
    return "warning"


def _normalize_link(raw_link: Any, *, item_label: str) -> NotificationPayload | None:
    if not isinstance(raw_link, Mapping):
        return None
    label = _normalize_string(raw_link.get("label"))
    url = _normalize_string(raw_link.get("url"))
    if not label or not url:
        return None
    if not _is_safe_url(url):
        logger.warning("Notification %s has unsafe link URL; dropping link", item_label)
        return None
    return {
        "label": html_lib.escape(label, quote=False),
        "url": url,
        "rel": LINK_REL,
    }


def _is_within_active_window(raw_item: Mapping[str, Any], *, item_label: str, now: datetime) -> bool:
    starts_at = _parse_optional_datetime(raw_item.get("startsAt"), item_label=item_label, field_name="startsAt")
    ends_at = _parse_optional_datetime(raw_item.get("endsAt"), item_label=item_label, field_name="endsAt")
    if starts_at is _INVALID_DATETIME or ends_at is _INVALID_DATETIME:
        return False
    if starts_at is not None and ends_at is not None and starts_at >= ends_at:
        logger.warning(
            "Notification %s has invalid date window: startsAt must be before endsAt; disabling item", item_label
        )
        return False
    if starts_at is not None and now < starts_at:
        return False
    return not (ends_at is not None and now >= ends_at)


def _normalize_optional_datetime(value: Any, *, item_label: str, field_name: str) -> str:
    parsed_datetime = _parse_optional_datetime(value, item_label=item_label, field_name=field_name)
    if parsed_datetime is None or parsed_datetime is _INVALID_DATETIME:
        return ""
    return parsed_datetime.isoformat().replace("+00:00", "Z")


class _InvalidDatetime:
    pass


_INVALID_DATETIME = _InvalidDatetime()


def _parse_optional_datetime(value: Any, *, item_label: str, field_name: str) -> datetime | None | _InvalidDatetime:
    raw_value = _normalize_string(value)
    if not raw_value:
        return None
    try:
        parsed_datetime = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Notification %s has invalid %s value %r; disabling item", item_label, field_name, raw_value)
        return _INVALID_DATETIME
    if parsed_datetime.tzinfo is None:
        return parsed_datetime.replace(tzinfo=timezone.utc)
    return parsed_datetime.astimezone(timezone.utc)


def _normalize_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _is_safe_url(url: str) -> bool:
    parsed_url = urlsplit(url)
    if parsed_url.scheme:
        return parsed_url.scheme.lower() in ALLOWED_URL_SCHEMES
    return not parsed_url.netloc


def _add_link_rel(sanitized_html: str) -> str:
    def replace_anchor(match: re.Match[str]) -> str:
        attributes = re.sub(r"\srel=(?:\"[^\"]*\"|'[^']*'|[^\s>]*)", "", match.group(1), flags=re.IGNORECASE)
        return f'<a{attributes} rel="{LINK_REL}">'

    return re.sub(r"<a\b([^>]*)>", replace_anchor, sanitized_html, flags=re.IGNORECASE)


def _normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_plain_text(value: Any) -> str:
    raw_value = _normalize_string(value)
    if not raw_value:
        return ""
    text_without_tags = re.sub(r"<[^>]*>", "", raw_value)
    return html_lib.unescape(text_without_tags).strip()
