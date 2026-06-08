import { URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';

const NAMESPACE = 'jupyterlab-rocm';

/**
 * Call the jupyterlab_rocm server extension REST API.
 *
 * @param endPoint path relative to the extension namespace
 * @param init request options
 */
export async function requestAPI<T>(
  endPoint = '',
  init: RequestInit = {}
): Promise<T> {
  const settings = ServerConnection.makeSettings();
  const requestUrl = URLExt.join(settings.baseUrl, NAMESPACE, endPoint);

  let response: Response;
  try {
    response = await ServerConnection.makeRequest(requestUrl, init, settings);
  } catch (error) {
    throw new ServerConnection.NetworkError(error as any);
  }

  let data: any = await response.text();
  if (data.length > 0) {
    try {
      data = JSON.parse(data);
    } catch (error) {
      console.error('jupyterlab-rocm: not a JSON response body.', response);
    }
  }

  if (!response.ok) {
    throw new ServerConnection.ResponseError(response, data.message || data);
  }

  return data as T;
}

/**
 * Build the WebSocket URL for the metrics stream, honouring the configured
 * base URL so it works behind JupyterHub / reverse proxies.
 */
export function streamUrl(intervalMs: number): string {
  const settings = ServerConnection.makeSettings();
  const base = URLExt.join(settings.wsUrl, NAMESPACE, 'stream');
  return `${base}?interval=${Math.round(intervalMs)}`;
}

/**
 * Build the download URL for a Cell Profile chrome trace, honouring the
 * configured base URL so it works behind JupyterHub / reverse proxies.
 */
export function traceUrl(jobId: string): string {
  const settings = ServerConnection.makeSettings();
  const base = URLExt.join(settings.baseUrl, NAMESPACE, 'profile', 'cell', 'trace');
  return `${base}?id=${encodeURIComponent(jobId)}`;
}

export interface ILiveProfileParams {
  kernel_id: string | null;
  window_s: number;
  warmup_s: number;
  options: Record<string, boolean>;
}

/** Trigger a live-capture run on the kernel's armed watcher. */
export async function liveProfile(
  params: ILiveProfileParams
): Promise<{ ok: boolean; armed: boolean }> {
  return requestAPI('profile/cell/live', {
    method: 'POST',
    body: JSON.stringify(params)
  });
}

/** Live-capture watcher status for the given kernel. */
export async function liveStatus(
  kernelId: string | null
): Promise<{ armed: boolean; busy: boolean }> {
  const q = kernelId ? `?kernel_id=${encodeURIComponent(kernelId)}` : '';
  return requestAPI(`profile/cell/live${q}`);
}
