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

import * as vscode from "vscode";
import {
  DEFAULT_RUNTIME_STATUS_SETTINGS,
  getRuntimeStatusText,
  parseRuntimeMetadata,
  shouldShowRuntimeStatus,
} from "@auplc/runtime-status";

const COMMAND_ID = "auplc.backToHub";
const STATUS_BAR_TEXT = "$(home) JupyterHub";
const RUNTIME_STATUS_BAR_TEXT_PREFIX = "$(clock)";
const RUNTIME_STATUS_BAR_UPDATE_INTERVAL_MS = DEFAULT_RUNTIME_STATUS_SETTINGS.updateIntervalMs;

function getHubUrl(): string {
  return process.env.AUPLC_HUB_URL?.trim() || "/hub/home";
}

function getAbsoluteHttpUri(url: string): vscode.Uri | undefined {
  let parsedUrl: URL;

  try {
    parsedUrl = new URL(url);
  } catch {
    return undefined;
  }

  if (parsedUrl.protocol !== "http:" && parsedUrl.protocol !== "https:") {
    return undefined;
  }

  return vscode.Uri.parse(parsedUrl.toString(), true);
}

function getInvalidHubUrlMessage(url: string): string {
  if (url.startsWith("/")) {
    return `AUPLC_HUB_URL is set to the relative path "${url}". Configure an absolute http(s) URL to enable the Back-to-Hub shortcut.`;
  }

  return `AUPLC_HUB_URL must be an absolute http(s) URL to enable the Back-to-Hub shortcut. Current value: "${url}".`;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function openHub(): Promise<void> {
  const hubUrl = getHubUrl();
  const hubUri = getAbsoluteHttpUri(hubUrl);

  if (!hubUri) {
    await vscode.window.showWarningMessage(getInvalidHubUrlMessage(hubUrl));
    return;
  }

  await vscode.env.openExternal(hubUri);
}

function handleOpenHubError(error: unknown): void {
  void vscode.window.showErrorMessage(`Unable to open JupyterHub: ${getErrorMessage(error)}`);
}

function createRuntimeStatusBarItem(context: vscode.ExtensionContext): void {
  const metadata = parseRuntimeMetadata(process.env);
  if (!shouldShowRuntimeStatus(metadata)) {
    return;
  }

  const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
  const updateStatusBarItem = () => {
    const nowSeconds = Math.floor(Date.now() / 1000);
    statusBarItem.text = `${RUNTIME_STATUS_BAR_TEXT_PREFIX} ${getRuntimeStatusText(metadata, nowSeconds)}`;
  };

  updateStatusBarItem();
  statusBarItem.tooltip = "Current server runtime remaining";
  statusBarItem.show();

  const interval = setInterval(updateStatusBarItem, RUNTIME_STATUS_BAR_UPDATE_INTERVAL_MS);
  const intervalDisposable = new vscode.Disposable(() => clearInterval(interval));

  context.subscriptions.push(statusBarItem, intervalDisposable);
}

export function activate(context: vscode.ExtensionContext): void {
  const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.text = STATUS_BAR_TEXT;
  statusBarItem.command = COMMAND_ID;
  statusBarItem.tooltip = "Back to JupyterHub";
  statusBarItem.show();

  const command = vscode.commands.registerCommand(COMMAND_ID, () => {
    void openHub().catch(handleOpenHubError);
  });

  context.subscriptions.push(statusBarItem, command);
  createRuntimeStatusBarItem(context);
}

export function deactivate(): void {}
