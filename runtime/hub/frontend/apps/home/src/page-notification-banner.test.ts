// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/react";

const templatePath = resolve(process.cwd(), "../../templates/page.html");

function extractNotificationBannerScript() {
  const template = readFileSync(templatePath, "utf8");
  const bannerBlockStart = template.indexOf("var severityLabels = {");
  const start = template.lastIndexOf("(function() {", bannerBlockStart);
  const end = template.indexOf("})();", bannerBlockStart);

  if (bannerBlockStart === -1 || start === -1 || end === -1) {
    throw new Error("Unable to locate notification banner script in page.html");
  }

  return template.slice(start, end + "})();".length).replaceAll("{{ base_url }}", "/hub/");
}

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

describe("notification banner inline script", () => {
  it("renders collapsed by default and toggles without any POST/dismiss call", async () => {
    document.body.innerHTML = '<div id="notification-banner-mount"></div>';
    window.jhdata = { user: "student" } as never;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/hub/api/notifications") {
        return jsonResponse({
          enabled: true,
          topbar: {
            id: "maintenance",
            version: "1",
            severity: "danger",
            dismissible: false,
            format: "markdown",
            titleHtml: "<strong>Urgent maintenance</strong>",
            messageHtml: "<p>Services restart in 10 minutes.</p>",
            link: {
              label: "Read details",
              url: "/hub/help",
              rel: "noopener noreferrer",
            },
            startsAt: null,
            endsAt: null,
          },
          homepage: {
            enabled: true,
            legacyAnnouncementFallback: true,
            items: [],
          },
        });
      }

      throw new Error(`Unexpected fetch: ${url} ${init?.method ?? "GET"}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    window.eval(extractNotificationBannerScript());

    await waitFor(() => {
      expect(document.querySelector('[data-testid="notification-banner"]')).toBeTruthy();
    });

    const banner = document.querySelector<HTMLElement>('[data-testid="notification-banner"]');
    const toggle = document.querySelector<HTMLButtonElement>('[data-testid="notification-banner-toggle"]');
    const body = document.querySelector<HTMLElement>('.notification-banner-body');

    expect(banner).not.toBeNull();
    expect(toggle).not.toBeNull();
    expect(body).not.toBeNull();
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    expect(toggle?.textContent).toBe("Details");
    expect(body?.hidden).toBe(true);
    expect(banner?.classList.contains("is-expanded")).toBe(false);

    toggle?.click();

    expect(toggle?.getAttribute("aria-expanded")).toBe("true");
    expect(toggle?.textContent).toBe("Hide");
    expect(body?.hidden).toBe(false);
    expect(banner?.classList.contains("is-expanded")).toBe(true);

    toggle?.click();

    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    expect(toggle?.textContent).toBe("Details");
    expect(body?.hidden).toBe(true);
    expect(banner?.classList.contains("is-expanded")).toBe(false);

    expect(fetchMock).toHaveBeenCalledWith(
      "/hub/api/notifications",
      expect.objectContaining({
        method: "GET",
        credentials: "same-origin",
      }),
    );
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
});
