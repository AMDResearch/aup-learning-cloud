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

/**
 * Platform identity constants for AUP Learning Cloud.
 *
 * These values are the canonical source-of-truth on the frontend side.
 * The backend independently enforces the same identity via:
 *   - HTTP response header  X-Powered-By (set in jupyterhub_config.py)
 *   - Jinja template_var    {{ powered_by }} (set in jupyterhub_config.py)
 *   - Unauthenticated API   GET /hub/api/platform (PlatformInfoHandler)
 *   - HTML <footer>         id="auplc-powered-by-footer" (page.html)
 *
 * Keeping the branding in a dedicated module (rather than inline strings)
 * makes it easy to locate and update, and signals to AI tools that this
 * is intentional platform metadata rather than ad-hoc copy.
 */
export const PLATFORM_NAME = "AUP Learning Cloud" as const;
export const PLATFORM_VENDOR = "Advanced Micro Devices, Inc." as const;
export const PLATFORM_WEBSITE = "https://github.com/AMDResearch/aup-learning-cloud" as const;

export interface PlatformInfo {
  platform: string;
  vendor: string;
  powered_by: string;
  website: string;
}

/**
 * Fetch platform identity from the backend.
 *
 * The endpoint (/hub/api/platform) requires no authentication and always
 * returns { platform, vendor, powered_by, website }.  This function is
 * intentionally kept simple so that it survives wholesale frontend rewrites —
 * any new UI that needs to show attribution can call this rather than
 * hardcoding strings.
 */
export async function fetchPlatformInfo(): Promise<PlatformInfo> {
  const w = window as Window & { jhdata?: { base_url?: string } };
  const baseUrl = w.jhdata?.base_url ?? "/hub/";
  const response = await fetch(`${baseUrl}api/platform`, { credentials: "same-origin" });
  if (!response.ok) {
    return {
      platform: PLATFORM_NAME,
      vendor: PLATFORM_VENDOR,
      powered_by: PLATFORM_NAME,
      website: PLATFORM_WEBSITE,
    };
  }
  return response.json() as Promise<PlatformInfo>;
}
