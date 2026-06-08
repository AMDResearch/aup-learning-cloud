import React, { useEffect, useRef, useState } from 'react';
import { Line } from 'react-chartjs-2';
import { ensureChartsRegistered } from '../chartSetup';
import { requestAPI, streamUrl } from '../handler';
import {
  IGpuProcess,
  IGpuSample,
  IGpusResponse,
  IMetricsSample
} from '../types';

ensureChartsRegistered();

const HISTORY = 60;

interface IGpuHistory {
  labels: number[];
  gfx: (number | null)[];
  vram: (number | null)[];
  power: (number | null)[];
  temp: (number | null)[];
}

function newHistory(): IGpuHistory {
  return { labels: [], gfx: [], vram: [], power: [], temp: [] };
}

function pushPoint(h: IGpuHistory, gpu: IGpuSample, t: number): void {
  h.labels.push(t);
  h.gfx.push(gpu.activity.gfx);
  h.vram.push(gpu.vram.percent);
  h.power.push(gpu.power.watts);
  h.temp.push(gpu.temperature_c);
  if (h.labels.length > HISTORY) {
    h.labels.shift();
    h.gfx.shift();
    h.vram.shift();
    h.power.shift();
    h.temp.shift();
  }
}

function fmt(value: number | null | undefined, unit = '', digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 'N/A';
  }
  return `${value.toFixed(digits)}${unit}`;
}

function fmtBytes(bytes: number | null | undefined, digits = 1): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) {
    return 'N/A';
  }
  return `${(bytes / 1048576).toFixed(digits)} MB`;
}

function fmtSdma(us: number | null | undefined): string {
  if (us === null || us === undefined || Number.isNaN(us)) {
    return 'N/A';
  }
  return `${us} us`;
}

function processDisplayName(name: string | null): string {
  if (name === null || name === undefined || name === '') {
    return 'N/A';
  }
  const base = name.split('/').pop() ?? name;
  return base || 'N/A';
}

interface IProcessRow {
  gpuIndex: number;
  gpuName: string;
  pid: IGpuProcess['pid'];
  name: IGpuProcess['name'];
  gtt_mem: IGpuProcess['gtt_mem'];
  vram_mem: IGpuProcess['vram_mem'];
  mem_usage: IGpuProcess['mem_usage'];
  cu_percent: IGpuProcess['cu_percent'];
  sdma_us: IGpuProcess['sdma_us'];
}

function collectProcessRows(gpus: IGpuSample[]): IProcessRow[] {
  const rows: IProcessRow[] = [];
  for (const gpu of gpus) {
    for (const proc of gpu.processes) {
      if (proc.pid == null || proc.pid <= 0) {
        continue;
      }
      rows.push({
        gpuIndex: gpu.index,
        gpuName: gpu.name,
        pid: proc.pid,
        name: proc.name,
        gtt_mem: proc.gtt_mem,
        vram_mem: proc.vram_mem,
        mem_usage: proc.mem_usage,
        cu_percent: proc.cu_percent,
        sdma_us: proc.sdma_us
      });
    }
  }
  return rows.sort(
    (a, b) =>
      a.gpuIndex - b.gpuIndex ||
      (a.pid ?? Number.MAX_SAFE_INTEGER) - (b.pid ?? Number.MAX_SAFE_INTEGER)
  );
}

// chart.js draws on a canvas and cannot resolve CSS variables, so resolve the
// JupyterLab theme variables to concrete colors (re-read each render so the
// charts follow light/dark theme switches).
function cssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') {
    return fallback;
  }
  const value = getComputedStyle(document.body).getPropertyValue(name).trim();
  return value || fallback;
}

const lineOptions = (suggestedMax?: number): any => {
  const tickColor = cssVar('--jp-ui-font-color2', '#616161');
  const gridColor = cssVar('--jp-border-color2', '#e0e0e0');
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { display: false },
      y: {
        beginAtZero: true,
        suggestedMax,
        ticks: { color: tickColor, maxTicksLimit: 4 },
        grid: { color: gridColor }
      }
    },
    elements: { point: { radius: 0 } }
  };
};

function MiniChart(props: {
  title: string;
  value: string;
  labels: number[];
  data: (number | null)[];
  color: string;
  suggestedMax?: number;
}): JSX.Element {
  const chartData = {
    labels: props.labels.map(() => ''),
    datasets: [
      {
        data: props.data,
        borderColor: props.color,
        backgroundColor: props.color + '33',
        borderWidth: 2,
        fill: true,
        tension: 0.25,
        spanGaps: true
      }
    ]
  };
  return (
    <div className="jp-rocm-metric">
      <div className="jp-rocm-metric-header">
        <span className="jp-rocm-metric-title">{props.title}</span>
        <span className="jp-rocm-metric-value">{props.value}</span>
      </div>
      <div className="jp-rocm-chart">
        <Line data={chartData} options={lineOptions(props.suggestedMax)} />
      </div>
    </div>
  );
}

function GpuCard(props: { gpu: IGpuSample; history: IGpuHistory }): JSX.Element {
  const { gpu, history } = props;
  return (
    <div className="jp-rocm-card">
      <div className="jp-rocm-card-title">
        <span className="jp-rocm-gpu-index">GPU {gpu.index}</span>
        <span className="jp-rocm-gpu-name">{gpu.name}</span>
      </div>
      <div className="jp-rocm-metrics">
        <MiniChart
          title="GFX Util"
          value={fmt(gpu.activity.gfx, '%')}
          labels={history.labels}
          data={history.gfx}
          color="#e8500e"
          suggestedMax={100}
        />
        <MiniChart
          title="VRAM"
          value={`${fmt(gpu.vram.percent, '%')} (${fmt(gpu.vram.used_mb, ' MB')})`}
          labels={history.labels}
          data={history.vram}
          color="#1f9d55"
          suggestedMax={100}
        />
        <MiniChart
          title="Power"
          value={fmt(gpu.power.watts, ' W', 1)}
          labels={history.labels}
          data={history.power}
          color="#3273dc"
        />
        <MiniChart
          title="Temp"
          value={fmt(gpu.temperature_c, ' \u00b0C')}
          labels={history.labels}
          data={history.temp}
          color="#b5179e"
        />
      </div>
      <div className="jp-rocm-extra">
        <span>
          Clock: {gpu.clock ? fmt(gpu.clock.cur_mhz, ' MHz') : 'N/A'}
        </span>
        <span>UMC: {fmt(gpu.activity.umc, '%')}</span>
      </div>
    </div>
  );
}

function ProcessSection(props: { gpus: IGpuSample[] }): JSX.Element {
  const rows = collectProcessRows(props.gpus);
  const gpuCount = props.gpus.length;

  return (
    <section className="jp-rocm-process-section">
      <div className="jp-rocm-process-header">
        <h3 className="jp-rocm-process-title">GPU Processes</h3>
        <span className="jp-rocm-process-meta">
          {rows.length} process{rows.length === 1 ? '' : 'es'} across{' '}
          {gpuCount} GPU{gpuCount === 1 ? '' : 's'}
        </span>
      </div>
      <div className="jp-rocm-process-table-wrap">
        <table className="jp-rocm-table jp-rocm-process-table">
            <thead>
              <tr>
                <th>GPU</th>
                <th className="jp-rocm-process-num">PID</th>
                <th>Process Name</th>
                <th className="jp-rocm-process-num">GTT_MEM</th>
                <th className="jp-rocm-process-num">VRAM_MEM</th>
                <th className="jp-rocm-process-num">MEM_USAGE</th>
                <th className="jp-rocm-process-num">CU %</th>
                <th className="jp-rocm-process-num">SDM</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={8}
                    className="jp-rocm-process-empty"
                  >
                    No running processes found
                  </td>
                </tr>
              ) : (
                rows.map(row => (
                  <tr
                    key={`${row.gpuIndex}-${row.pid ?? 'na'}-${row.name ?? ''}`}
                  >
                    <td
                      className="jp-rocm-process-gpu"
                      title={row.gpuName}
                    >
                      {row.gpuIndex}
                    </td>
                    <td className="jp-rocm-process-num">
                      {row.pid ?? 'N/A'}
                    </td>
                    <td className="jp-rocm-proc-name" title={row.name ?? ''}>
                      {processDisplayName(row.name)}
                    </td>
                    <td className="jp-rocm-process-num">
                      {fmtBytes(row.gtt_mem)}
                    </td>
                    <td className="jp-rocm-process-num">
                      {fmtBytes(row.vram_mem)}
                    </td>
                    <td className="jp-rocm-process-num">
                      {fmtBytes(row.mem_usage)}
                    </td>
                    <td className="jp-rocm-process-num">
                      {fmt(row.cu_percent, '%', 1)}
                    </td>
                    <td className="jp-rocm-process-num">
                      {fmtSdma(row.sdma_us)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
    </section>
  );
}

export function Dashboard(): JSX.Element {
  const [sample, setSample] = useState<IMetricsSample | null>(null);
  const [connected, setConnected] = useState(false);
  const [info, setInfo] = useState<IGpusResponse | null>(null);
  const [interval, setIntervalMs] = useState(1000);
  const historyRef = useRef<Map<number, IGpuHistory>>(new Map());
  const wsRef = useRef<WebSocket | null>(null);
  const [, forceRender] = useState(0);

  useEffect(() => {
    let active = true;
    requestAPI<IGpusResponse>('gpus')
      .then(res => {
        if (active) {
          setInfo(res);
        }
      })
      .catch(err => console.error('jupyterlab-rocm: failed to load gpus', err));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let closedByUs = false;
    let reconnectTimer: number | undefined;

    const connect = (): void => {
      const ws = new WebSocket(streamUrl(interval));
      wsRef.current = ws;
      ws.onopen = () => {
        if (!closedByUs) {
          setConnected(true);
        }
      };
      ws.onclose = () => {
        if (closedByUs) {
          return;
        }
        setConnected(false);
        reconnectTimer = window.setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = evt => {
        if (closedByUs) {
          return;
        }
        try {
          const data = JSON.parse(evt.data) as IMetricsSample;
          const t = data.timestamp ?? Date.now() / 1000;
          for (const gpu of data.gpus || []) {
            let h = historyRef.current.get(gpu.index);
            if (!h) {
              h = newHistory();
              historyRef.current.set(gpu.index, h);
            }
            pushPoint(h, gpu, t);
          }
          setSample(data);
          forceRender(n => n + 1);
        } catch (err) {
          console.error('jupyterlab-rocm: bad message', err);
        }
      };
    };

    connect();
    return () => {
      closedByUs = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      const ws = wsRef.current;
      if (ws) {
        // Detach handlers so no late events fire after unmount.
        ws.onopen = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.onmessage = null;
        ws.close();
      }
    };
  }, [interval]);

  const unavailable = sample && !sample.available;

  return (
    <div className="jp-rocm-dashboard">
      <div className="jp-rocm-toolbar">
        <span
          className={`jp-rocm-status ${connected ? 'connected' : 'disconnected'}`}
        >
          {connected ? 'Live' : 'Reconnecting...'}
        </span>
        <label className="jp-rocm-interval">
          Interval
          <select
            value={interval}
            onChange={e => setIntervalMs(parseInt(e.target.value, 10))}
          >
            <option value={500}>0.5s</option>
            <option value={1000}>1s</option>
            <option value={2000}>2s</option>
            <option value={5000}>5s</option>
          </select>
        </label>
        {info?.rocprof && !info.rocprof.available && (
          <span className="jp-rocm-warn">rocprofv3 not found</span>
        )}
      </div>

      {unavailable && (
        <div className="jp-rocm-error">
          <strong>AMD GPU metrics unavailable.</strong>
          <p>{sample?.error}</p>
        </div>
      )}

      {!sample && !unavailable && (
        <div className="jp-rocm-loading">Connecting to GPU metrics...</div>
      )}

      <div className="jp-rocm-cards">
        {sample?.gpus?.map(gpu => (
          <GpuCard
            key={gpu.index}
            gpu={gpu}
            history={historyRef.current.get(gpu.index) ?? newHistory()}
          />
        ))}
      </div>

      {sample?.available && sample.gpus.length > 0 && (
        <ProcessSection gpus={sample.gpus} />
      )}
    </div>
  );
}
