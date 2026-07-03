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

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { act } from "react";

const sharedMocks = vi.hoisted(() => ({
  fetchPlatformInfo: vi.fn(),
  getNotifications: vi.fn(),
  getMyQuota: vi.fn(),
  getMyUsage: vi.fn(),
  getResources: vi.fn(),
  getResourceType: vi.fn(),
  getResourceTypeLabel: vi.fn(),
}));

vi.mock("@auplc/shared", () => ({
  PLATFORM_NAME: "AUP Learning Cloud",
  fetchPlatformInfo: sharedMocks.fetchPlatformInfo,
  getNotifications: sharedMocks.getNotifications,
  getMyQuota: sharedMocks.getMyQuota,
  getMyUsage: sharedMocks.getMyUsage,
  getResources: sharedMocks.getResources,
  getResourceType: sharedMocks.getResourceType,
  getResourceTypeLabel: sharedMocks.getResourceTypeLabel,
}));

vi.mock("./onboarding-launch-workspace.png", () => ({
  default: "onboarding-launch-workspace.png",
}));
vi.mock("./onboarding-resource-picker.png", () => ({
  default: "onboarding-resource-picker.png",
}));
vi.mock("./onboarding-developer-program-qr.png", () => ({
  default: "onboarding-developer-program-qr.png",
}));

type NotificationResponse = {
  enabled: boolean;
  topbar: null;
  homepage: {
    enabled: boolean;
    legacyAnnouncementFallback: boolean;
    items: Array<{
      id: string;
      version: string;
      severity: "info" | "success" | "warning" | "danger";
      dismissible: boolean;
      format: "text" | "markdown" | "html";
      eyebrow?: string;
      titleHtml: string;
      messageHtml: string;
      link: null;
      startsAt: string | null;
      endsAt: string | null;
    }>;
  };
};

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });

  return { promise, resolve, reject };
}

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

function textResponse(body: string) {
  return {
    ok: true,
    status: 200,
    text: async () => body,
  } as Response;
}

async function renderApp() {
  vi.resetModules();
  const { default: App } = await import("./App");
  return render(<App />);
}

beforeEach(() => {
  vi.clearAllMocks();

  sharedMocks.fetchPlatformInfo.mockResolvedValue({
    platform: "AUP Learning Cloud",
  });
  sharedMocks.getMyQuota.mockResolvedValue(null);
  sharedMocks.getMyUsage.mockResolvedValue(null);
  sharedMocks.getResources.mockResolvedValue({ groups: [] });
  sharedMocks.getResourceType.mockReturnValue("code");
  sharedMocks.getResourceTypeLabel.mockReturnValue("Code Resource");

  window.localStorage.clear();
  window.jhdata = {
    base_url: "/hub/",
    xsrf_token: "test-xsrf",
    user: "student",
  } as never;
  window.HOME_DATA = {
    server_active: false,
    server_url: "/hub/user/student/",
  } as never;
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    media: "(prefers-color-scheme: dark)",
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  });
});

describe("App homepage notifications", () => {
  it("renders structured homepage announcements in one focusable updates rail", async () => {
    const notifications: NotificationResponse = {
      enabled: true,
      topbar: null,
      homepage: {
        enabled: true,
        legacyAnnouncementFallback: true,
        items: [
          {
            id: "platform-welcome",
            version: "1",
            severity: "info",
            dismissible: false,
            format: "markdown",
            eyebrow: "Platform",
            titleHtml: "<p>Welcome to AUP Learning Cloud</p>",
            messageHtml: "<p>Get started with GPU-accelerated Jupyter notebooks powered by AMD ROCm technology.</p>",
            link: null,
            startsAt: null,
            endsAt: null,
          },
          {
            id: "maintenance",
            version: "1",
            severity: "warning",
            dismissible: false,
            format: "markdown",
            titleHtml: "<strong>Scheduled maintenance</strong>",
            messageHtml: "<p>Maintenance starts at 10:00 UTC.</p>",
            link: null,
            startsAt: null,
            endsAt: null,
          },
        ],
      },
    };

    const quota = deferred<null>();
    const resources = deferred<{ groups: [] }>();
    const notificationsDeferred = deferred<NotificationResponse>();
    const onboarding = deferred<Response>();
    const user = deferred<Response>();

    sharedMocks.getMyQuota.mockReturnValueOnce(quota.promise);
    sharedMocks.getResources.mockReturnValueOnce(resources.promise);
    sharedMocks.getNotifications.mockReturnValueOnce(notificationsDeferred.promise);

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/hub/api/onboarding/me") {
        return onboarding.promise;
      }
      if (url === "/hub/api/users/student") {
        return user.promise;
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url} ${init?.method ?? "GET"}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    await renderApp();

    await act(async () => {
      quota.resolve(null);
      resources.resolve({ groups: [] });
      notificationsDeferred.resolve(notifications);
      onboarding.resolve(jsonResponse({ should_show: false, dismissed_at: null }) as unknown as Response);
      user.resolve(jsonResponse({ server: false }) as unknown as Response);
      await Promise.resolve();
    });

    const updatesRail = await screen.findByRole("region", { name: /News & Updates/i });
    expect(updatesRail.getAttribute("tabindex")).toBe("0");
    expect(within(updatesRail).getAllByText("Welcome to AUP Learning Cloud")).toHaveLength(1);
    expect(within(updatesRail).getByText("Platform").textContent).toBe("Platform");
    expect(within(updatesRail).getByRole("heading", { name: /Scheduled maintenance/i })).not.toBeNull();
    expect(within(updatesRail).getByText("Announcement").textContent).toBe("Announcement");
    expect(within(updatesRail).getByText(/Maintenance starts at 10:00 UTC\./i).textContent).toContain("Maintenance starts at 10:00 UTC.");
    expect(screen.queryByRole("heading", { name: /Platform Announcement/i })).toBeNull();
    expect(screen.queryByText(/Legacy announcement should not appear/i)).toBeNull();
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/hub/static/announcement.txt")).toBe(false);
    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== "POST")).toBe(true);
  });

  it("falls back to announcement.txt when notifications API fails", async () => {
    const quota = deferred<null>();
    const resources = deferred<{ groups: [] }>();
    const notificationsDeferred = deferred<NotificationResponse>();
    const onboarding = deferred<Response>();
    const user = deferred<Response>();
    const announcement = deferred<Response>();

    sharedMocks.getMyQuota.mockReturnValueOnce(quota.promise);
    sharedMocks.getResources.mockReturnValueOnce(resources.promise);
    sharedMocks.getNotifications.mockReturnValueOnce(notificationsDeferred.promise);

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/hub/api/onboarding/me") {
        return onboarding.promise;
      }
      if (url === "/hub/static/announcement.txt") {
        return announcement.promise;
      }
      if (url === "/hub/api/users/student") {
        return user.promise;
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url} ${init?.method ?? "GET"}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    await renderApp();

    await act(async () => {
      quota.resolve(null);
      resources.resolve({ groups: [] });
      notificationsDeferred.reject(new Error("notifications unavailable"));
      await Promise.resolve();
      onboarding.resolve(jsonResponse({ should_show: false, dismissed_at: null }) as unknown as Response);
      user.resolve(jsonResponse({ server: false }) as unknown as Response);
      announcement.resolve(textResponse("Legacy announcement fallback") as unknown as Response);
      await Promise.resolve();
    });

    expect(await screen.findByRole("heading", { name: /Platform Announcement/i })).not.toBeNull();
    expect(screen.getByText("Legacy announcement fallback").textContent).toBe("Legacy announcement fallback");
    expect(screen.queryByRole("heading", { name: /Scheduled maintenance/i })).toBeNull();
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/hub/static/announcement.txt")).toBe(true);
    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== "POST")).toBe(true);
  });

  it("falls back to announcement.txt when homepage items are empty and fallback is enabled", async () => {
    const quota = deferred<null>();
    const resources = deferred<{ groups: [] }>();
    const notificationsDeferred = deferred<NotificationResponse>();
    const onboarding = deferred<Response>();
    const user = deferred<Response>();
    const announcement = deferred<Response>();

    sharedMocks.getMyQuota.mockReturnValueOnce(quota.promise);
    sharedMocks.getResources.mockReturnValueOnce(resources.promise);
    sharedMocks.getNotifications.mockReturnValueOnce(notificationsDeferred.promise);

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/hub/api/onboarding/me") {
        return onboarding.promise;
      }
      if (url === "/hub/static/announcement.txt") {
        return announcement.promise;
      }
      if (url === "/hub/api/users/student") {
        return user.promise;
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url} ${init?.method ?? "GET"}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    await renderApp();

    await act(async () => {
      quota.resolve(null);
      resources.resolve({ groups: [] });
      notificationsDeferred.resolve({
        enabled: true,
        topbar: null,
        homepage: {
          enabled: true,
          legacyAnnouncementFallback: true,
          items: [],
        },
      });
      await Promise.resolve();
      onboarding.resolve(jsonResponse({ should_show: false, dismissed_at: null }) as unknown as Response);
      user.resolve(jsonResponse({ server: false }) as unknown as Response);
      announcement.resolve(textResponse("Legacy empty-state fallback") as unknown as Response);
      await Promise.resolve();
    });

    expect(await screen.findByRole("heading", { name: /Platform Announcement/i })).not.toBeNull();
    expect(screen.getByText("Legacy empty-state fallback").textContent).toBe("Legacy empty-state fallback");
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/hub/static/announcement.txt")).toBe(true);
    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== "POST")).toBe(true);
  });
});
