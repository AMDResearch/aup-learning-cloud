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
