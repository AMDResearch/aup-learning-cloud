import { INotebookTracker } from '@jupyterlab/notebook';
import { ISettingRegistry } from '@jupyterlab/settingregistry';
import React, { useEffect, useRef, useState } from 'react';
import { Bar } from 'react-chartjs-2';
import {
  CellProfileMode,
  DEFAULT_CELL_PROFILE_SETTINGS,
  ICellProfileSettings,
  PLUGIN_ID,
  readCellProfileSettings
} from '../cellProfileSettings';
import { ensureChartsRegistered } from '../chartSetup';
import { liveProfile, liveStatus, requestAPI, traceUrl } from '../handler';
import { IKernelStat, IOperatorStat, IProfileJob } from '../types';

ensureChartsRegistered();

function nsToMs(ns: number): number {
  return ns / 1e6;
}

function fmtDuration(ns: number): string {
  if (ns >= 1e9) {
    return `${(ns / 1e9).toFixed(3)} s`;
  }
  if (ns >= 1e6) {
    return `${(ns / 1e6).toFixed(3)} ms`;
  }
  if (ns >= 1e3) {
    return `${(ns / 1e3).toFixed(2)} us`;
  }
  return `${ns.toFixed(0)} ns`;
}

function fmtBytes(num: number): string {
  const sign = num < 0 ? '-' : '';
  let value = Math.abs(num);
  const units = ['B', 'KB', 'MB', 'GB'];
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 ? 0 : 2;
  return `${sign}${value.toFixed(digits)} ${units[unit]}`;
}

function shortName(name: string): string {
  const trimmed = name.length > 48 ? name.slice(0, 45) + '...' : name;
  return trimmed;
}

type OperatorSort = 'self_gpu_ns' | 'gpu_total_ns' | 'self_cpu_ns' | 'cpu_total_ns';

function modeLabel(job: IProfileJob): string {
  const extra = job.extra || {};
  if (extra.mode === 'live') {
    const warm = extra.warmup_s ? `, warmup ${extra.warmup_s}s` : '';
    return `live capture (${extra.window_s}s${warm}, approx)`;
  }
  return 'full cell';
}

function cssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') {
    return fallback;
  }
  const value = getComputedStyle(document.body).getPropertyValue(name).trim();
  return value || fallback;
}

function KernelChart(props: { kernels: IKernelStat[] }): JSX.Element {
  const top = props.kernels.slice(0, 10);
  const data = {
    labels: top.map(k => shortName(k.name)),
    datasets: [
      {
        label: 'Total time (ms)',
        data: top.map(k => nsToMs(k.total_ns)),
        backgroundColor: cssVar('--jp-rocm-cell-profile-accent', '#1976d2')
      }
    ]
  };
  const options: any = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: {
        beginAtZero: true,
        ticks: { color: cssVar('--jp-ui-font-color2', '#616161') },
        grid: { color: cssVar('--jp-border-color2', '#e0e0e0') }
      },
      y: { ticks: { color: cssVar('--jp-ui-font-color1', '#212121') } }
    }
  };
  return (
    <div className="jp-rocm-kernel-chart">
      <Bar data={data} options={options} />
    </div>
  );
}

function OperatorTable(props: {
  operators: IOperatorStat[];
  sort: OperatorSort;
  onSort: (s: OperatorSort) => void;
}): JSX.Element {
  const { operators, sort, onSort } = props;
  const showMemory = operators.some(o => o.self_cpu_mem || o.self_gpu_mem);
  const showShapes = operators.some(o => o.input_shapes);
  const sorted = [...operators].sort((a, b) => b[sort] - a[sort]);

  const sortable = (label: string, key: OperatorSort): JSX.Element => (
    <th
      className={`jp-rocm-sortable${sort === key ? ' active' : ''}`}
      onClick={() => onSort(key)}
      title="Sort by this column"
    >
      {label}
      {sort === key ? ' \u25BC' : ''}
    </th>
  );

  return (
    <table className="jp-rocm-table jp-rocm-op-table">
      <thead>
        <tr>
          <th>Operator</th>
          <th>Calls</th>
          {sortable('Self CPU', 'self_cpu_ns')}
          {sortable('CPU total', 'cpu_total_ns')}
          {sortable('Self GPU', 'self_gpu_ns')}
          {sortable('GPU total', 'gpu_total_ns')}
          <th>%</th>
          {showMemory && <th>Self CPU Mem</th>}
          {showMemory && <th>Self GPU Mem</th>}
          {showShapes && <th>Input Shapes</th>}
        </tr>
      </thead>
      <tbody>
        {sorted.slice(0, 50).map((op, i) => (
          <tr key={`${op.name}-${i}`}>
            <td
              title={op.stack ? op.stack.join('\n') : op.name}
              className="jp-rocm-kname"
            >
              {shortName(op.name)}
            </td>
            <td>{op.calls}</td>
            <td>{fmtDuration(op.self_cpu_ns)}</td>
            <td>{fmtDuration(op.cpu_total_ns)}</td>
            <td>{fmtDuration(op.self_gpu_ns)}</td>
            <td>{fmtDuration(op.gpu_total_ns)}</td>
            <td>{op.percent.toFixed(1)}</td>
            {showMemory && <td>{fmtBytes(op.self_cpu_mem)}</td>}
            {showMemory && <td>{fmtBytes(op.self_gpu_mem)}</td>}
            {showShapes && (
              <td className="jp-rocm-kname" title={op.input_shapes ?? ''}>
                {op.input_shapes ?? ''}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function JobResults(props: { job: IProfileJob }): JSX.Element {
  const job = props.job;
  const [opSort, setOpSort] = useState<OperatorSort>('self_gpu_ns');
  const traceAvailable = !!job.extra?.trace_available;
  const approx = !!job.extra?.approx;

  return (
    <div className="jp-rocm-job">
      <div className="jp-rocm-job-head">
        <span className={`jp-rocm-badge ${job.status}`}>{job.status}</span>
        <span className="jp-rocm-mode">{modeLabel(job)}</span>
        {traceAvailable && (
          <a
            className="jp-rocm-trace-link"
            href={traceUrl(job.id)}
            target="_blank"
            rel="noreferrer"
            download
          >
            Download trace
          </a>
        )}
      </div>

      {approx && (
        <div className="jp-rocm-hint">
          Live-capture results are a sample of a fixed wall-clock window; GPU work
          is asynchronous so totals are approximate.
        </div>
      )}

      {job.status === 'error' && (
        <div className="jp-rocm-error">
          <p>{job.error}</p>
          {job.stderr && <pre className="jp-rocm-log">{job.stderr}</pre>}
        </div>
      )}

      {job.summary && (
        <div className="jp-rocm-summary">
          {job.summary.operator_count !== undefined && (
            <span>Operators: {job.summary.operator_count}</span>
          )}
          <span>Kernels: {job.summary.kernel_count}</span>
          <span>Dispatches: {job.summary.total_dispatches}</span>
          {job.summary.self_cpu_total_ns !== undefined && (
            <span>Self CPU: {fmtDuration(job.summary.self_cpu_total_ns)}</span>
          )}
          {job.summary.self_gpu_total_ns !== undefined && (
            <span>Self GPU: {fmtDuration(job.summary.self_gpu_total_ns)}</span>
          )}
          <span>Total GPU time: {fmtDuration(job.summary.total_kernel_ns)}</span>
        </div>
      )}

      {job.operators && job.operators.length > 0 && (
        <>
          <div className="jp-rocm-section-title">Operators</div>
          <OperatorTable
            operators={job.operators}
            sort={opSort}
            onSort={setOpSort}
          />
        </>
      )}

      {job.kernels && job.kernels.length > 0 && (
        <>
          <div className="jp-rocm-section-title">GPU kernels</div>
          <KernelChart kernels={job.kernels} />
          <table className="jp-rocm-table">
            <thead>
              <tr>
                <th>Kernel</th>
                <th>Calls</th>
                <th>Total</th>
                <th>Avg</th>
                <th>%</th>
              </tr>
            </thead>
            <tbody>
              {job.kernels.slice(0, 50).map(k => (
                <tr key={k.name}>
                  <td title={k.name} className="jp-rocm-kname">
                    {shortName(k.name)}
                  </td>
                  <td>{k.calls}</td>
                  <td>{fmtDuration(k.total_ns)}</td>
                  <td>{fmtDuration(k.avg_ns)}</td>
                  <td>{k.percent.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {job.status === 'done' &&
        (!job.kernels || job.kernels.length === 0) &&
        (!job.operators || job.operators.length === 0) && (
          <div className="jp-rocm-loading">
            {job.extra?.mode === 'live'
              ? 'The live window captured no GPU work. The kernel may have been idle; trigger Profile now while the cell is actively running on the GPU.'
              : 'No kernel dispatches were captured. Make sure the cell launches GPU work.'}
          </div>
        )}
    </div>
  );
}

function CaptureOptions(props: {
  values: ICellProfileSettings;
  update: <K extends keyof ICellProfileSettings>(
    key: K,
    value: ICellProfileSettings[K]
  ) => void;
}): JSX.Element {
  const { values, update } = props;
  return (
    <div className="jp-rocm-cp-row jp-rocm-cp-checks">
      <label>
        <input
          type="checkbox"
          checked={values.recordShapes}
          onChange={e => update('recordShapes', e.target.checked)}
        />
        Shapes
      </label>
      <label>
        <input
          type="checkbox"
          checked={values.profileMemory}
          onChange={e => update('profileMemory', e.target.checked)}
        />
        Memory
      </label>
      <label>
        <input
          type="checkbox"
          checked={values.withStack}
          onChange={e => update('withStack', e.target.checked)}
        />
        Stack
      </label>
      <label>
        <input
          type="checkbox"
          checked={values.keepTrace}
          onChange={e => update('keepTrace', e.target.checked)}
        />
        Keep trace
      </label>
    </div>
  );
}

function CellProfilePanel(props: {
  settingRegistry: ISettingRegistry | null;
  notebooks: INotebookTracker | null;
}): JSX.Element {
  const { notebooks } = props;
  const [settings, setSettings] = useState<ISettingRegistry.ISettings | null>(
    null
  );
  const [values, setValues] = useState<ICellProfileSettings>(
    DEFAULT_CELL_PROFILE_SETTINGS
  );
  const [armed, setArmed] = useState<boolean>(false);
  const [busy, setBusy] = useState<boolean>(false);
  const [pending, setPending] = useState<boolean>(false);
  const [message, setMessage] = useState<string>('');
  const pendingTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!props.settingRegistry) {
      return;
    }
    let mounted = true;
    void props.settingRegistry
      .load(PLUGIN_ID)
      .then(loaded => {
        if (!mounted) {
          return;
        }
        setSettings(loaded);
        setValues(readCellProfileSettings(loaded));
        loaded.changed.connect(() => setValues(readCellProfileSettings(loaded)));
      })
      .catch(err => console.warn('jupyterlab-rocm: settings unavailable', err));
    return () => {
      mounted = false;
    };
  }, [props.settingRegistry]);

  const isLive = values.cellProfileMode === 'live';

  const kernelId = (): string | null =>
    notebooks?.currentWidget?.sessionContext.session?.kernel?.id ?? null;

  // Poll armed/busy only while the live mode is selected.
  useEffect(() => {
    if (!isLive) {
      setBusy(false);
      return;
    }
    let active = true;
    const poll = async (): Promise<void> => {
      try {
        const res = await liveStatus(kernelId());
        if (!active) {
          return;
        }
        setArmed(!!res.armed);
        setBusy(!!res.busy);
        if (res.busy) {
          // Server confirms a capture is running; clear the optimistic flag.
          setPending(false);
        }
      } catch {
        if (active) {
          setArmed(false);
        }
      }
    };
    void poll();
    const id = window.setInterval(poll, 1500);
    return () => {
      active = false;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLive, notebooks]);

  useEffect(
    () => () => {
      if (pendingTimer.current) {
        window.clearTimeout(pendingTimer.current);
      }
    },
    []
  );

  const update = <K extends keyof ICellProfileSettings>(
    key: K,
    value: ICellProfileSettings[K]
  ): void => {
    setValues(prev => ({ ...prev, [key]: value }));
    if (settings) {
      void settings.set(key, value as any);
    }
  };

  const enableLive = (): void => {
    const kernel = notebooks?.currentWidget?.sessionContext.session?.kernel;
    if (!kernel) {
      setMessage('No active kernel. Open a notebook and select its tab first.');
      return;
    }
    kernel.requestExecute({
      code: '%load_ext jupyterlab_rocm',
      silent: true,
      store_history: false
    });
    setMessage('Arming live capture... do this before starting a long cell.');
  };

  const profileNow = async (): Promise<void> => {
    setPending(true);
    setMessage(`Capturing ${values.timeWindowSeconds}s...`);
    if (pendingTimer.current) {
      window.clearTimeout(pendingTimer.current);
    }
    // Fallback so the button re-enables even if we miss the busy transition.
    pendingTimer.current = window.setTimeout(
      () => setPending(false),
      (values.timeWindowSeconds + values.timeWarmupSeconds + 10) * 1000
    );
    try {
      const res = await liveProfile({
        kernel_id: kernelId(),
        window_s: values.timeWindowSeconds,
        warmup_s: values.timeWarmupSeconds,
        options: {
          record_shapes: values.recordShapes,
          profile_memory: values.profileMemory,
          with_stack: values.withStack,
          keep_trace: values.keepTrace
        }
      });
      if (!res.armed) {
        setPending(false);
        setMessage('No armed watcher. Click "Enable live capture" first.');
      }
    } catch (err) {
      setPending(false);
      setMessage(`Live capture request failed: ${String(err)}`);
    }
  };

  if (!props.settingRegistry) {
    return (
      <p className="jp-rocm-hint">
        Settings registry unavailable; the Cell Profile button uses the default
        full-cell mode. Use <code>%%rocprofv3</code> flags to choose a mode.
      </p>
    );
  }

  return (
    <div className="jp-rocm-cp-settings">
      <label className="jp-rocm-cp-field">
        Mode
        <select
          value={values.cellProfileMode}
          onChange={e =>
            update('cellProfileMode', e.target.value as CellProfileMode)
          }
        >
          <option value="full">Full cell (short cells, use the button)</option>
          <option value="live">Live capture (running cell)</option>
        </select>
      </label>

      {values.cellProfileMode === 'full' && (
        <p className="jp-rocm-cp-note">
          Click the <b>Cell Profile</b> button in the notebook toolbar to profile
          the whole run. Best for short, self-contained cells. For a long-running
          training loop, switch to <b>Live capture</b>.
        </p>
      )}

      {isLive && (
        <div className="jp-rocm-live">
          <div className="jp-rocm-live-head">
            <span
              className={`jp-rocm-live-dot ${armed ? 'on' : 'off'}`}
              title={armed ? 'Watcher armed' : 'Watcher not armed'}
            />
            <span className="jp-rocm-live-state">
              {armed ? (busy ? 'capturing...' : 'armed') : 'not armed'}
            </span>
          </div>
          <div className="jp-rocm-cp-row">
            <label className="jp-rocm-cp-field">
              Seconds
              <input
                type="number"
                min={0.1}
                step={0.5}
                value={values.timeWindowSeconds}
                onChange={e => update('timeWindowSeconds', Number(e.target.value))}
              />
            </label>
            <label className="jp-rocm-cp-field">
              Warmup (s)
              <input
                type="number"
                min={0}
                step={0.5}
                value={values.timeWarmupSeconds}
                onChange={e => update('timeWarmupSeconds', Number(e.target.value))}
              />
            </label>
          </div>
          <p className="jp-rocm-cp-note">
            Start your long-running cell, then click Profile now to grab a{' '}
            {values.timeWindowSeconds}s sample. No code edit, no warmup wait,
            and training keeps running.
          </p>
          <div className="jp-rocm-cp-row">
            <button
              className="jp-rocm-live-btn"
              onClick={() => void profileNow()}
              disabled={!armed || busy || pending}
              title={
                !armed
                  ? 'Enable live capture first'
                  : busy || pending
                    ? 'A capture is already running'
                    : 'Capture now'
              }
            >
              {busy || pending ? 'Capturing...' : 'Profile now'}
            </button>
            {!armed && (
              <button className="jp-rocm-live-btn" onClick={enableLive}>
                Enable live capture
              </button>
            )}
          </div>
          {message && <p className="jp-rocm-cp-note">{message}</p>}
        </div>
      )}

      <CaptureOptions values={values} update={update} />
    </div>
  );
}

export function Profiler(props: {
  settingRegistry?: ISettingRegistry | null;
  notebooks?: INotebookTracker | null;
}): JSX.Element {
  const settingRegistry = props.settingRegistry ?? null;
  const notebooks = props.notebooks ?? null;
  const [jobs, setJobs] = useState<IProfileJob[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    const load = async (): Promise<void> => {
      try {
        const res = await requestAPI<{ jobs: IProfileJob[] }>('profile/cell');
        setJobs(res.jobs || []);
      } catch (err) {
        console.error('jupyterlab-rocm: cell jobs', err);
      }
    };
    void load();
    timer.current = window.setInterval(load, 3000);
    return () => {
      if (timer.current) {
        window.clearInterval(timer.current);
      }
    };
  }, []);

  const current = jobs.find(j => j.id === selected) || jobs[0] || null;

  return (
    <div className="jp-rocm-profiler">
      <div className="jp-rocm-cell-profile">
        <h3>Cell Profile</h3>
        <p className="jp-rocm-hint">
          Click the <b>Cell Profile</b> button in the notebook toolbar on the
          active code cell (or use <code>%%rocprofv3</code>). PyTorch GPU cells
          are profiled with <code>torch.profiler</code> in the live kernel.
          Results appear under the cell and here.
        </p>
        <CellProfilePanel
          settingRegistry={settingRegistry}
          notebooks={notebooks}
        />
        {jobs.length > 1 && (
          <label className="jp-rocm-cell-select">
            Result
            <select
              value={current?.id ?? ''}
              onChange={e => setSelected(e.target.value)}
            >
              {jobs.map(j => (
                <option key={j.id} value={j.id}>
                  {new Date(j.created * 1000).toLocaleTimeString()} &mdash;{' '}
                  {j.preset}
                </option>
              ))}
            </select>
          </label>
        )}
        {current ? (
          <JobResults job={current} />
        ) : (
          <div className="jp-rocm-loading">
            No Cell Profile results yet. Click <b>Cell Profile</b> on a PyTorch
            GPU cell.
          </div>
        )}
      </div>
    </div>
  );
}
