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

import { describe, expect, it, vi } from "vitest";

vi.mock("@jupyterlab/settingregistry", () => ({
  ISettingRegistry: Symbol("ISettingRegistry"),
}));

vi.mock("@jupyterlab/statusbar", () => ({
  IStatusBar: Symbol("IStatusBar"),
}));

import { activateRuntimeStatus } from "./index.js";

describe("JupyterLab runtime status activation", () => {
  it("returns safely without fetching metadata when the status bar is unavailable", async () => {
    const fetchMetadata = vi.fn(async () => ({ startTimeSeconds: 100, runTimeMinutes: 30 }));

    await expect(activateRuntimeStatus(null, null, { fetchMetadata })).resolves.toBeUndefined();
    expect(fetchMetadata).not.toHaveBeenCalled();
  });

  it("registers a hidden item and does not crash when metadata is unavailable", async () => {
    vi.useFakeTimers();
    const registered = vi.fn();
    const statusBar = { registerStatusItem: registered };
    const fetchMetadata = vi.fn(async () => undefined);

    const item = await activateRuntimeStatus(statusBar as never, null, {
      fetchMetadata,
      nowSeconds: () => 200,
    });
    await item?.refreshMetadata();

    expect(registered).toHaveBeenCalledWith(
      "auplc-runtime-status",
      expect.objectContaining({ item, align: "left", rank: 1 }),
    );
    expect(fetchMetadata).toHaveBeenCalled();
    expect(item?.node.hidden).toBe(true);
    expect(item?.node.textContent).toBe("");

    item?.dispose();
    vi.useRealTimers();
  });
});
