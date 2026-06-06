import React, { useEffect, useRef, useState } from 'react';
import { Bar } from 'react-chartjs-2';
import { ensureChartsRegistered } from '../chartSetup';
import { requestAPI } from '../handler';
import { IKernelStat, IProfileJob, IRocprofStatus } from '../types';

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

function shortName(name: string): string {
  const trimmed = name.length > 48 ? name.slice(0, 45) + '...' : name;
  return trimmed;
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
        backgroundColor: '#e8500e'
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

function JobResults(props: { job: IProfileJob }): JSX.Element {
  const job = props.job;
  return (
    <div className="jp-rocm-job">
      <div className="jp-rocm-job-head">
        <span className={`jp-rocm-badge ${job.status}`}>{job.status}</span>
        <code className="jp-rocm-cmd">{job.command}</code>
      </div>

      {job.status === 'error' && (
        <div className="jp-rocm-error">
          <p>{job.error}</p>
          {job.stderr && <pre className="jp-rocm-log">{job.stderr}</pre>}
        </div>
      )}

      {job.summary && (
        <div className="jp-rocm-summary">
          <span>Kernels: {job.summary.kernel_count}</span>
          <span>Dispatches: {job.summary.total_dispatches}</span>
          <span>Total GPU time: {fmtDuration(job.summary.total_kernel_ns)}</span>
        </div>
      )}

      {job.kernels && job.kernels.length > 0 && (
        <>
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

      {job.status === 'done' && (!job.kernels || job.kernels.length === 0) && (
        <div className="jp-rocm-loading">
          No kernel dispatches were captured. Try the "kernel" or "sys" preset,
          or verify the target actually launches GPU kernels.
        </div>
      )}
    </div>
  );
}

function CellProfiling(props: { rocprof: IRocprofStatus | null }): JSX.Element {
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
  const attach = props.rocprof?.attach;

  return (
    <div className="jp-rocm-cell-profiling">
      <h3>Cell profiling (live attach)</h3>
      {attach && !attach.supported && attach.hint && (
        <div className="jp-rocm-error">{attach.hint}</div>
      )}
      {attach && attach.supported && !attach.tool_attach_env && attach.hint && (
        <div className="jp-rocm-loading">{attach.hint}</div>
      )}
      <p className="jp-rocm-hint">
        Put <code>%load_ext jupyterlab_rocm</code> in a cell, then start a cell
        with <code>%%rocprofv3</code> &mdash; or click <b>Profile cell</b> in the
        notebook toolbar. The cell runs in the live kernel (state is preserved)
        and results appear below.
      </p>
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
          No cell profiles yet. Run a cell with <code>%%rocprofv3</code>.
        </div>
      )}
    </div>
  );
}

export function Profiler(props: {
  getCurrentNotebook: () => string | null;
}): JSX.Element {
  const [targetType, setTargetType] = useState<'notebook' | 'script' | 'command'>(
    'notebook'
  );
  const [target, setTarget] = useState('');
  const [preset, setPreset] = useState('runtime');
  const [includeRegex, setIncludeRegex] = useState('');
  const [excludeRegex, setExcludeRegex] = useState('');
  const [job, setJob] = useState<IProfileJob | null>(null);
  const [rocprof, setRocprof] = useState<IRocprofStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    requestAPI<{ rocprof: IRocprofStatus }>('profile')
      .then(res => setRocprof(res.rocprof))
      .catch(err => console.error('jupyterlab-rocm: profile status', err));
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
      }
    };
  }, []);

  const useCurrentNotebook = (): void => {
    const path = props.getCurrentNotebook();
    if (path) {
      setTargetType('notebook');
      setTarget(path);
    } else {
      setError('No notebook is currently active.');
    }
  };

  const poll = (id: string): void => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
    }
    pollRef.current = window.setInterval(async () => {
      try {
        const updated = await requestAPI<IProfileJob>(`profile/${id}`);
        setJob(updated);
        if (updated.status === 'done' || updated.status === 'error') {
          if (pollRef.current) {
            window.clearInterval(pollRef.current);
          }
        }
      } catch (err) {
        console.error('jupyterlab-rocm: poll failed', err);
      }
    }, 1000);
  };

  const start = async (): Promise<void> => {
    setError(null);
    if (!target) {
      setError('Please provide a target.');
      return;
    }
    const extra: Record<string, unknown> = {};
    if (includeRegex) {
      extra.kernel_include_regex = includeRegex;
    }
    if (excludeRegex) {
      extra.kernel_exclude_regex = excludeRegex;
    }
    try {
      const created = await requestAPI<IProfileJob>('profile', {
        method: 'POST',
        body: JSON.stringify({
          target_type: targetType,
          target,
          preset,
          extra
        })
      });
      setJob(created);
      poll(created.id);
    } catch (err: any) {
      setError(err?.message || String(err));
    }
  };

  const running = job && (job.status === 'queued' || job.status === 'running');

  return (
    <div className="jp-rocm-profiler">
      <CellProfiling rocprof={rocprof} />

      <h3>rocprofv3 Profiler</h3>
      {rocprof && !rocprof.available && (
        <div className="jp-rocm-error">{rocprof.error}</div>
      )}

      <div className="jp-rocm-form">
        <label>
          Target type
          <select
            value={targetType}
            onChange={e => setTargetType(e.target.value as any)}
          >
            <option value="notebook">Notebook (.ipynb)</option>
            <option value="script">Python script (.py)</option>
            <option value="command">Custom command</option>
          </select>
        </label>
        <label className="jp-rocm-target">
          Target
          <input
            type="text"
            value={target}
            placeholder={
              targetType === 'command'
                ? 'e.g. python train.py --epochs 1'
                : 'absolute or workspace-relative path'
            }
            onChange={e => setTarget(e.target.value)}
          />
        </label>
        {targetType === 'notebook' && (
          <button className="jp-rocm-link-btn" onClick={useCurrentNotebook}>
            Use current notebook
          </button>
        )}
        <label>
          Trace preset
          <select value={preset} onChange={e => setPreset(e.target.value)}>
            {(rocprof?.presets ?? ['runtime', 'kernel', 'sys', 'hip']).map(p => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label>
          Include kernels (regex)
          <input
            type="text"
            value={includeRegex}
            placeholder="optional"
            onChange={e => setIncludeRegex(e.target.value)}
          />
        </label>
        <label>
          Exclude kernels (regex)
          <input
            type="text"
            value={excludeRegex}
            placeholder="optional"
            onChange={e => setExcludeRegex(e.target.value)}
          />
        </label>
        <button
          className="jp-rocm-run-btn"
          onClick={start}
          disabled={!!running || (rocprof ? !rocprof.available : false)}
        >
          {running ? 'Profiling...' : 'Run profiling'}
        </button>
      </div>

      {error && <div className="jp-rocm-error">{error}</div>}

      {job && <JobResults job={job} />}
    </div>
  );
}
