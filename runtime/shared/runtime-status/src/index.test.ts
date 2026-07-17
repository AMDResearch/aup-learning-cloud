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

import { describe, expect, it } from "vitest";

import {
  DEFAULT_RUNTIME_STATUS_SETTINGS,
  calculateRuntimeElapsedSeconds,
  calculateRuntimeRemainingSeconds,
  formatRuntimeRemaining,
  getRuntimeStatusText,
  normalizeRuntimeStatusSettings,
  parseRuntimeMetadata,
  renderRuntimeStatusTemplate,
  shouldShowRuntimeStatus,
} from "./index.js";

describe("runtime metadata parsing", () => {
  it("parses valid finite metadata from environment variable names", () => {
    expect(parseRuntimeMetadata({ JOB_START_TIME: "100", JOB_RUN_TIME: "30" })).toEqual({
      kind: "finite",
      startTimeSeconds: 100,
      runTimeMinutes: 30,
    });
  });

  it("parses valid finite metadata from direct property names", () => {
    expect(parseRuntimeMetadata({ startTimeSeconds: 200, runTimeMinutes: 45 })).toEqual({
      kind: "finite",
      startTimeSeconds: 200,
      runTimeMinutes: 45,
    });
  });

  it("rejects missing start time", () => {
    expect(parseRuntimeMetadata({ JOB_RUN_TIME: "30" })).toBeUndefined();
  });

  it("rejects missing runtime", () => {
    expect(parseRuntimeMetadata({ JOB_START_TIME: "100" })).toBeUndefined();
  });

  it("rejects invalid, zero, and negative finite values", () => {
    expect(parseRuntimeMetadata({ JOB_START_TIME: "abc", JOB_RUN_TIME: "30" })).toBeUndefined();
    expect(parseRuntimeMetadata({ JOB_START_TIME: "0", JOB_RUN_TIME: "30" })).toBeUndefined();
    expect(parseRuntimeMetadata({ JOB_START_TIME: "100", JOB_RUN_TIME: "0" })).toBeUndefined();
    expect(parseRuntimeMetadata({ JOB_START_TIME: "-1", JOB_RUN_TIME: "30" })).toBeUndefined();
    expect(parseRuntimeMetadata({ JOB_START_TIME: "100", JOB_RUN_TIME: "-1" })).toBeUndefined();
    expect(parseRuntimeMetadata({ JOB_START_TIME: "Infinity", JOB_RUN_TIME: "30" })).toBeUndefined();
  });

  it("treats the runtime-unlimited flag as unlimited instead of finite", () => {
    expect(
      parseRuntimeMetadata({
        AUPLC_RUNTIME_UNLIMITED: "true",
        JOB_START_TIME: "100",
        JOB_RUN_TIME: "30",
      }),
    ).toEqual({ kind: "unlimited" });
  });
});

describe("runtime calculations", () => {
  const metadata = { kind: "finite" as const, startTimeSeconds: 100, runTimeMinutes: 30 };

  it("calculates elapsed and remaining seconds for finite metadata", () => {
    expect(calculateRuntimeElapsedSeconds(metadata, 160)).toBe(60);
    expect(calculateRuntimeRemainingSeconds(metadata, 160)).toBe(1740);
  });

  it("clamps remaining seconds at zero", () => {
    expect(calculateRuntimeRemainingSeconds(metadata, 2_000)).toBe(0);
  });

  it("formats remaining time as HH:MM:SS under and over one hour", () => {
    expect(formatRuntimeRemaining(59)).toBe("00:00:59");
    expect(formatRuntimeRemaining(3_661)).toBe("01:01:01");
    expect(formatRuntimeRemaining(90_061)).toBe("25:01:01");
  });
});

describe("template rendering", () => {
  const metadata = { kind: "finite" as const, startTimeSeconds: 100, runTimeMinutes: 30 };

  it("uses the required default settings", () => {
    expect(DEFAULT_RUNTIME_STATUS_SETTINGS).toEqual({
      template: "Runtime: {remaining}",
      hideWhenUnavailable: true,
      hideWhenUnlimited: true,
      updateIntervalMs: 1000,
    });
  });

  it("normalizes update intervals with a 250 ms minimum", () => {
    expect(normalizeRuntimeStatusSettings({ updateIntervalMs: 10 })).toMatchObject({ updateIntervalMs: 250 });
    expect(normalizeRuntimeStatusSettings({ updateIntervalMs: 500 })).toMatchObject({ updateIntervalMs: 500 });
  });

  it("renders all supported global template tokens", () => {
    expect(
      renderRuntimeStatusTemplate(
        "Runtime: {remaining} left ({remainingSeconds}s/{totalMinutes}m/{elapsedSeconds}s used)",
        metadata,
        160,
      ),
    ).toBe("Runtime: 00:29:00 left (1740s/30m/60s used)");
  });

  it("preserves unknown template tokens unchanged", () => {
    expect(renderRuntimeStatusTemplate("Runtime: {remaining} {unknown}", metadata, 160)).toBe(
      "Runtime: 00:29:00 {unknown}",
    );
  });

  it("renders the default runtime status text", () => {
    expect(getRuntimeStatusText(metadata, 160)).toBe("Runtime: 00:29:00");
  });
});

describe("visibility decisions", () => {
  const finiteMetadata = { kind: "finite" as const, startTimeSeconds: 100, runTimeMinutes: 30 };
  const unlimitedMetadata = { kind: "unlimited" as const };

  it("shows finite runtime metadata", () => {
    expect(shouldShowRuntimeStatus(finiteMetadata)).toBe(true);
  });

  it("hides unavailable metadata by default and can show it when configured", () => {
    expect(shouldShowRuntimeStatus(undefined)).toBe(false);
    expect(shouldShowRuntimeStatus(undefined, { hideWhenUnavailable: false })).toBe(true);
  });

  it("hides unlimited metadata by default and can show it when configured", () => {
    expect(shouldShowRuntimeStatus(unlimitedMetadata)).toBe(false);
    expect(shouldShowRuntimeStatus(unlimitedMetadata, { hideWhenUnlimited: false })).toBe(true);
  });
});
