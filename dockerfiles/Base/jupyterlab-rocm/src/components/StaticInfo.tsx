import React, { useEffect, useState } from 'react';
import { requestAPI } from '../handler';
import { IStaticResponse } from '../types';

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

function isPlainObject(value: any): boolean {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

// Render a "leaf" value (scalar, {value, unit}, or array of scalars).
function renderScalar(value: any): string {
  if (value === null || value === undefined) {
    return 'N/A';
  }
  if (Array.isArray(value)) {
    return value.map(v => renderScalar(v)).join(', ');
  }
  if (isPlainObject(value)) {
    // Common amd-smi shape: { value, unit }
    if ('value' in value && 'unit' in value && Object.keys(value).length === 2) {
      return `${renderScalar(value.value)} ${value.unit}`;
    }
    return JSON.stringify(value);
  }
  return String(value);
}

function isLeafArray(value: any): boolean {
  return (
    Array.isArray(value) && value.every(v => !isPlainObject(v) && !Array.isArray(v))
  );
}

function KeyValueTable(props: { data: Record<string, any> }): JSX.Element {
  const entries = Object.entries(props.data);
  const scalars = entries.filter(
    ([, v]) => !isPlainObject(v) && (!Array.isArray(v) || isLeafArray(v))
  );
  const nested = entries.filter(
    ([, v]) => isPlainObject(v) || (Array.isArray(v) && !isLeafArray(v))
  );

  return (
    <>
      {scalars.length > 0 && (
        <table className="jp-rocm-table jp-rocm-info-table">
          <tbody>
            {scalars.map(([k, v]) => (
              <tr key={k}>
                <td className="jp-rocm-info-key">{humanizeKey(k)}</td>
                <td className="jp-rocm-info-val">{renderScalar(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {nested.map(([k, v]) => (
        <div key={k} className="jp-rocm-info-subsection">
          <h5>{humanizeKey(k)}</h5>
          {Array.isArray(v) ? (
            v.map((item, i) => (
              <KeyValueTable key={i} data={item as Record<string, any>} />
            ))
          ) : (
            <KeyValueTable data={v as Record<string, any>} />
          )}
        </div>
      ))}
    </>
  );
}

function Section(props: {
  title: string;
  data: Record<string, any>;
  defaultOpen?: boolean;
}): JSX.Element {
  const [open, setOpen] = useState(props.defaultOpen ?? false);
  return (
    <div className="jp-rocm-info-section">
      <button className="jp-rocm-info-toggle" onClick={() => setOpen(o => !o)}>
        <span className="jp-rocm-info-caret">{open ? '\u25be' : '\u25b8'}</span>
        {props.title}
      </button>
      {open && (
        <div className="jp-rocm-info-body">
          <KeyValueTable data={props.data} />
        </div>
      )}
    </div>
  );
}

export function StaticInfo(): JSX.Element {
  const [data, setData] = useState<IStaticResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = (): void => {
    setLoading(true);
    requestAPI<IStaticResponse>('static')
      .then(res => {
        setData(res);
        setError(res.error);
      })
      .catch(err => setError(err?.message || String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="jp-rocm-static">
      <div className="jp-rocm-toolbar">
        <h3>GPU Information</h3>
        <button className="jp-rocm-link-btn" onClick={load}>
          Refresh
        </button>
      </div>

      {loading && <div className="jp-rocm-loading">Loading amd-smi data...</div>}
      {error && <div className="jp-rocm-error">{error}</div>}

      {data &&
        !data.available &&
        !error && <div className="jp-rocm-error">amd-smi is not available.</div>}

      {data?.static?.map((gpu, idx) => {
        const listEntry = data.list?.find(l => l.gpu === gpu.gpu) || data.list?.[idx];
        const name = gpu?.asic?.market_name || `GPU ${gpu.gpu ?? idx}`;
        const { gpu: _gpuIdx, ...sections } = gpu;
        return (
          <div key={idx} className="jp-rocm-info-gpu">
            <div className="jp-rocm-card-title">
              <span className="jp-rocm-gpu-index">GPU {gpu.gpu ?? idx}</span>
              <span className="jp-rocm-gpu-name">{name}</span>
            </div>
            {listEntry && (
              <Section
                title="Identification (amd-smi list)"
                data={listEntry}
                defaultOpen={true}
              />
            )}
            {Object.entries(sections).map(([key, value]) => (
              <Section
                key={key}
                title={humanizeKey(key)}
                data={
                  isPlainObject(value)
                    ? (value as Record<string, any>)
                    : { [key]: value }
                }
                defaultOpen={key === 'asic'}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
