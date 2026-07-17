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
import { render, screen } from "@testing-library/react";
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
  sharedMocks.getNotifications.mockResolvedValue({
    enabled: true,
    topbar: null,
    homepage: {
      enabled: true,
      legacyAnnouncementFallback: false,
      items: [],
    },
  });
  sharedMocks.getMyQuota.mockResolvedValue(null);
  sharedMocks.getMyUsage.mockResolvedValue(null);
  sharedMocks.getResourceType.mockReturnValue("notebook");
  sharedMocks.getResourceTypeLabel.mockReturnValue("Notebook");

  window.localStorage.clear();
  window.AVAILABLE_RESOURCES = undefined;
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

  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/hub/api/onboarding/me") {
      return Promise.resolve(jsonResponse({ should_show: false, dismissed_at: null }));
    }
    return Promise.reject(new Error(`Unexpected fetch: ${url} ${init?.method ?? "GET"}`));
  }));
});

describe("App resource list", () => {
  it("renders all non-empty groups returned by getResources when window.AVAILABLE_RESOURCES is stale", async () => {
    window.AVAILABLE_RESOURCES = ["gpu-course"];

    const platformInfo = deferred<{ platform: string }>();
    const quota = deferred<null>();
    const notifications = deferred<{
      enabled: boolean;
      topbar: null;
      homepage: {
        enabled: boolean;
        legacyAnnouncementFallback: boolean;
        items: [];
      };
    }>();
    const resources = deferred<{
      resources: [];
      acceleratorKeys: [];
      allowedGitProviders: [];
      allowPersistenceChoice: boolean;
      defaultPersistence: boolean;
      groups: Array<{
        name: string;
        displayName: string;
        resources: Array<{
          key: string;
          image: string;
          requirements: {
            cpu: string;
            memory: string;
            "amd.com/gpu"?: string;
          };
          metadata: {
            group: string;
            description: string;
            subDescription: string;
          };
        }>;
      }>;
    }>();
    const onboarding = deferred<Response>();

    sharedMocks.fetchPlatformInfo.mockReturnValueOnce(platformInfo.promise);
    sharedMocks.getMyQuota.mockReturnValueOnce(quota.promise);
    sharedMocks.getNotifications.mockReturnValueOnce(notifications.promise);
    sharedMocks.getResources.mockReturnValueOnce(resources.promise);

    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/hub/api/onboarding/me") {
        return onboarding.promise;
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url} ${init?.method ?? "GET"}`));
    }));

    await renderApp();

    await act(async () => {
      platformInfo.resolve({ platform: "AUP Learning Cloud" });
      quota.resolve(null);
      notifications.resolve({
        enabled: true,
        topbar: null,
        homepage: {
          enabled: true,
          legacyAnnouncementFallback: false,
          items: [],
        },
      });
      resources.resolve({
        resources: [],
        acceleratorKeys: [],
        allowedGitProviders: [],
        allowPersistenceChoice: false,
        defaultPersistence: false,
        groups: [
          {
            name: "accelerated-courses",
            displayName: "Accelerated Courses",
            resources: [
              {
                key: "gpu-course",
                image: "ghcr.io/example/gpu-course:test",
                requirements: {
                  cpu: "2",
                  memory: "8Gi",
                  "amd.com/gpu": "1",
                },
                metadata: {
                  group: "accelerated-courses",
                  description: "GPU Course from API",
                  subDescription: "Visible because the backend returned it",
                },
              },
            ],
          },
          {
            name: "cpu-courses",
            displayName: "CPU Courses",
            resources: [
              {
                key: "cpu-course",
                image: "ghcr.io/example/cpu-course:test",
                requirements: {
                  cpu: "1",
                  memory: "4Gi",
                },
                metadata: {
                  group: "cpu-courses",
                  description: "CPU Course from API",
                  subDescription: "Would be hidden by stale client-side filtering",
                },
              },
            ],
          },
        ],
      });
      onboarding.resolve(jsonResponse({ should_show: false, dismissed_at: null }) as unknown as Response);
      await Promise.resolve();
    });

    expect(await screen.findByRole("heading", { name: "GPU Course from API" })).not.toBeNull();
    expect(await screen.findByRole("heading", { name: "CPU Course from API" })).not.toBeNull();
    expect(screen.getByRole("heading", { name: "Accelerated Courses" })).not.toBeNull();
    expect(screen.getByRole("heading", { name: "CPU Courses" })).not.toBeNull();
  });
});
