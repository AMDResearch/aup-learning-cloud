import React, { useEffect, useRef, useState } from 'react';
import { Bar } from 'react-chartjs-2';
import { ensureChartsRegistered } from '../chartSetup';
import { requestAPI } from '../handler';
import { IKernelStat, IProfileJob } from '../types';

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

function JobResults(props: { job: IProfileJob }): JSX.Element {
  const job = props.job;
  return (
    <div className="jp-rocm-job">
      <div className="jp-rocm-job-head">
        <span className={`jp-rocm-badge ${job.status}`}>{job.status}</span>
        {job.command ? <code className="jp-rocm-cmd">{job.command}</code> : null}
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
          No kernel dispatches were captured. Make sure the cell launches GPU
          work.
        </div>
      )}
    </div>
  );
}

export function Profiler(): JSX.Element {
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
          Click the floating <b>Cell Profile</b> button beside the active code
          cell (or use <code>%%rocprofv3</code>). PyTorch GPU cells are profiled
          with <code>torch.profiler</code> in the live kernel. Results appear
          under the cell and here.
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
            No Cell Profile results yet. Click <b>Cell Profile</b> on a PyTorch
            GPU cell.
          </div>
        )}
      </div>
    </div>
  );
}
