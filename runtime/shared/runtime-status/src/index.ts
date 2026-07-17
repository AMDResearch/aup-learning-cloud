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

export interface FiniteRuntimeMetadata {
  kind: "finite";
  startTimeSeconds: number;
  runTimeMinutes: number;
}

export interface UnlimitedRuntimeMetadata {
  kind: "unlimited";
}

export type RuntimeMetadata = FiniteRuntimeMetadata | UnlimitedRuntimeMetadata;

export interface RuntimeMetadataSource {
  startTimeSeconds?: unknown;
  runTimeMinutes?: unknown;
  runtimeUnlimited?: unknown;
  unlimited?: unknown;
  JOB_START_TIME?: unknown;
  JOB_RUN_TIME?: unknown;
  AUPLC_RUNTIME_UNLIMITED?: unknown;
}

export interface RuntimeStatusSettings {
  template: string;
  hideWhenUnavailable: boolean;
  hideWhenUnlimited: boolean;
  updateIntervalMs: number;
}

export type RuntimeStatusSettingsInput = Partial<RuntimeStatusSettings>;

export const DEFAULT_RUNTIME_STATUS_SETTINGS: RuntimeStatusSettings = {
  template: "Runtime: {remaining}",
  hideWhenUnavailable: true,
  hideWhenUnlimited: true,
  updateIntervalMs: 1000,
};

export const MIN_RUNTIME_STATUS_UPDATE_INTERVAL_MS = 250;

function parseFiniteNumber(value: unknown): number | undefined {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : undefined;
  }

  if (typeof value !== "string") {
    return undefined;
  }

  const trimmedValue = value.trim();
  if (trimmedValue.length === 0) {
    return undefined;
  }

  const parsedValue = Number(trimmedValue);
  return Number.isFinite(parsedValue) ? parsedValue : undefined;
}

function parseBooleanFlag(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "number") {
    return value === 1;
  }

  if (typeof value !== "string") {
    return false;
  }

  const normalizedValue = value.trim().toLowerCase();
  return normalizedValue === "true" || normalizedValue === "1" || normalizedValue === "yes";
}

function getSourceValue(source: RuntimeMetadataSource, directName: keyof RuntimeMetadataSource, envName: keyof RuntimeMetadataSource): unknown {
  return source[directName] ?? source[envName];
}

export function normalizeRuntimeStatusSettings(settings: RuntimeStatusSettingsInput = {}): RuntimeStatusSettings {
  const configuredInterval = parseFiniteNumber(settings.updateIntervalMs);
  const updateIntervalMs = Math.max(
    MIN_RUNTIME_STATUS_UPDATE_INTERVAL_MS,
    Math.floor(configuredInterval ?? DEFAULT_RUNTIME_STATUS_SETTINGS.updateIntervalMs),
  );

  return {
    template: settings.template ?? DEFAULT_RUNTIME_STATUS_SETTINGS.template,
    hideWhenUnavailable: settings.hideWhenUnavailable ?? DEFAULT_RUNTIME_STATUS_SETTINGS.hideWhenUnavailable,
    hideWhenUnlimited: settings.hideWhenUnlimited ?? DEFAULT_RUNTIME_STATUS_SETTINGS.hideWhenUnlimited,
    updateIntervalMs,
  };
}

export function parseRuntimeMetadata(source: RuntimeMetadataSource): RuntimeMetadata | undefined {
  const runtimeUnlimited =
    parseBooleanFlag(source.runtimeUnlimited) ||
    parseBooleanFlag(source.unlimited) ||
    parseBooleanFlag(source.AUPLC_RUNTIME_UNLIMITED);

  if (runtimeUnlimited) {
    return { kind: "unlimited" };
  }

  const startTimeSeconds = parseFiniteNumber(getSourceValue(source, "startTimeSeconds", "JOB_START_TIME"));
  const runTimeMinutes = parseFiniteNumber(getSourceValue(source, "runTimeMinutes", "JOB_RUN_TIME"));

  if (startTimeSeconds === undefined || startTimeSeconds <= 0 || runTimeMinutes === undefined || runTimeMinutes <= 0) {
    return undefined;
  }

  return {
    kind: "finite",
    startTimeSeconds,
    runTimeMinutes,
  };
}

export function calculateRuntimeElapsedSeconds(metadata: FiniteRuntimeMetadata, nowSeconds: number): number {
  return Math.max(0, Math.floor(nowSeconds - metadata.startTimeSeconds));
}

export function calculateRuntimeRemainingSeconds(metadata: FiniteRuntimeMetadata, nowSeconds: number): number {
  const totalSeconds = metadata.runTimeMinutes * 60;
  const elapsedSeconds = nowSeconds - metadata.startTimeSeconds;
  return Math.max(0, Math.floor(totalSeconds - elapsedSeconds));
}

export function formatRuntimeRemaining(remainingSeconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(remainingSeconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  return [hours, minutes, seconds].map((part) => String(part).padStart(2, "0")).join(":");
}

export function shouldShowRuntimeStatus(
  metadata: RuntimeMetadata | undefined,
  settings: RuntimeStatusSettingsInput = {},
): boolean {
  const normalizedSettings = normalizeRuntimeStatusSettings(settings);

  if (!metadata) {
    return !normalizedSettings.hideWhenUnavailable;
  }

  if (metadata.kind === "unlimited") {
    return !normalizedSettings.hideWhenUnlimited;
  }

  return true;
}

export function renderRuntimeStatusTemplate(template: string, metadata: RuntimeMetadata | undefined, nowSeconds: number): string {
  return template.replace(/\{[A-Za-z]+\}/g, (token) => {
    if (!metadata) {
      return token;
    }

    if (metadata.kind === "unlimited") {
      return token === "{remaining}" ? "Unlimited" : token;
    }

    switch (token) {
      case "{remaining}":
        return formatRuntimeRemaining(calculateRuntimeRemainingSeconds(metadata, nowSeconds));
      case "{remainingSeconds}":
        return String(calculateRuntimeRemainingSeconds(metadata, nowSeconds));
      case "{totalMinutes}":
        return String(metadata.runTimeMinutes);
      case "{elapsedSeconds}":
        return String(calculateRuntimeElapsedSeconds(metadata, nowSeconds));
      default:
        return token;
    }
  });
}

export function getRuntimeStatusText(
  metadata: RuntimeMetadata | undefined,
  nowSeconds: number,
  settings: RuntimeStatusSettingsInput = {},
): string {
  const normalizedSettings = normalizeRuntimeStatusSettings(settings);
  return renderRuntimeStatusTemplate(normalizedSettings.template, metadata, nowSeconds);
}
