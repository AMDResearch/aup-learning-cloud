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

import type { JupyterFrontEnd, JupyterFrontEndPlugin } from "@jupyterlab/application";
import { URLExt } from "@jupyterlab/coreutils";
import { ServerConnection } from "@jupyterlab/services";
import type { ISettingRegistry } from "@jupyterlab/settingregistry";
import { ISettingRegistry as SettingRegistryToken } from "@jupyterlab/settingregistry";
import type { IStatusBar } from "@jupyterlab/statusbar";
import { IStatusBar as StatusBarToken } from "@jupyterlab/statusbar";
import {
  DEFAULT_RUNTIME_STATUS_SETTINGS,
  getRuntimeStatusText,
  normalizeRuntimeStatusSettings,
  parseRuntimeMetadata,
  shouldShowRuntimeStatus,
  type RuntimeMetadata,
  type RuntimeMetadataSource,
  type RuntimeStatusSettings,
  type RuntimeStatusSettingsInput,
} from "@auplc/runtime-status";
import { Widget } from "@lumino/widgets";

export const PLUGIN_ID = "@auplc/jupyterlab-runtime-status:plugin";
export const METADATA_ENDPOINT = "auplc/runtime-status/api/metadata";

type MetadataFetcher = () => Promise<RuntimeMetadataSource | undefined>;

interface RuntimeStatusItemOptions {
  fetchMetadata: MetadataFetcher;
  initialSettings?: RuntimeStatusSettingsInput;
  nowSeconds?: () => number;
}

export class RuntimeStatusItem extends Widget {
  private metadata: RuntimeMetadata | undefined;
  private settings: RuntimeStatusSettings;
  private timer: number | undefined;
  private readonly fetchMetadata: MetadataFetcher;
  private readonly nowSeconds: () => number;

  constructor(options: RuntimeStatusItemOptions) {
    super();
    this.fetchMetadata = options.fetchMetadata;
    this.settings = normalizeRuntimeStatusSettings(options.initialSettings);
    this.nowSeconds = options.nowSeconds ?? (() => Math.floor(Date.now() / 1000));
    this.id = "auplc-jupyterlab-runtime-status";
    this.node.dataset.jpStatusItem = "auplc-runtime-status";
    this.node.className = "auplc-jupyterlab-runtime-status";
    this.node.setAttribute("aria-live", "polite");
    this.render();
    void this.refreshMetadata();
    this.resetTimer();
  }

  setSettings(settings: RuntimeStatusSettingsInput): void {
    this.settings = normalizeRuntimeStatusSettings(settings);
    this.render();
    this.resetTimer();
  }

  async refreshMetadata(): Promise<void> {
    try {
      const source = await this.fetchMetadata();
      this.metadata = source ? parseRuntimeMetadata(source) : undefined;
    } catch {
      this.metadata = undefined;
    }
    this.render();
  }

  protected onBeforeDetach(): void {
    this.clearTimer();
  }

  dispose(): void {
    this.clearTimer();
    super.dispose();
  }

  private resetTimer(): void {
    this.clearTimer();
    this.timer = window.setInterval(() => this.render(), this.settings.updateIntervalMs);
  }

  private clearTimer(): void {
    if (this.timer !== undefined) {
      window.clearInterval(this.timer);
      this.timer = undefined;
    }
  }

  private render(): void {
    const visible = shouldShowRuntimeStatus(this.metadata, this.settings);
    this.node.hidden = !visible;
    this.node.textContent = visible
      ? getRuntimeStatusText(this.metadata, this.nowSeconds(), this.settings)
      : "";
  }
}

export async function fetchRuntimeMetadata(): Promise<RuntimeMetadataSource | undefined> {
  const settings = ServerConnection.makeSettings();
  const requestUrl = URLExt.join(settings.baseUrl, METADATA_ENDPOINT);
  const response = await ServerConnection.makeRequest(requestUrl, {}, settings);

  if (!response.ok) {
    return undefined;
  }

  return (await response.json()) as RuntimeMetadataSource;
}

function settingsFromRegistry(settings: ISettingRegistry.ISettings | undefined): RuntimeStatusSettingsInput {
  if (!settings) {
    return DEFAULT_RUNTIME_STATUS_SETTINGS;
  }

  const { template, hideWhenUnavailable, hideWhenUnlimited, updateIntervalMs } = settings.composite;

  return {
    template: typeof template === "string" ? template : undefined,
    hideWhenUnavailable: typeof hideWhenUnavailable === "boolean" ? hideWhenUnavailable : undefined,
    hideWhenUnlimited: typeof hideWhenUnlimited === "boolean" ? hideWhenUnlimited : undefined,
    updateIntervalMs: typeof updateIntervalMs === "number" ? updateIntervalMs : undefined,
  };
}

export async function activateRuntimeStatus(
  statusBar: IStatusBar | null,
  settingRegistry: ISettingRegistry | null,
  options: Partial<RuntimeStatusItemOptions> = {},
): Promise<RuntimeStatusItem | undefined> {
  if (!statusBar) {
    return undefined;
  }

  const item = new RuntimeStatusItem({
    fetchMetadata: options.fetchMetadata ?? fetchRuntimeMetadata,
    initialSettings: options.initialSettings,
    nowSeconds: options.nowSeconds,
  });

  statusBar.registerStatusItem("auplc-runtime-status", {
    align: "left",
    item,
    rank: 1,
  });

  if (settingRegistry) {
    try {
      const loadedSettings = await settingRegistry.load(PLUGIN_ID);
      item.setSettings(settingsFromRegistry(loadedSettings));
      loadedSettings.changed.connect(() => {
        item.setSettings(settingsFromRegistry(loadedSettings));
      });
    } catch {
      item.setSettings(DEFAULT_RUNTIME_STATUS_SETTINGS);
    }
  }

  return item;
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: PLUGIN_ID,
  autoStart: true,
  optional: [StatusBarToken, SettingRegistryToken],
  activate: (_app: JupyterFrontEnd, statusBar: IStatusBar | null, settingRegistry: ISettingRegistry | null) => {
    void activateRuntimeStatus(statusBar, settingRegistry);
  },
};

export default plugin;
