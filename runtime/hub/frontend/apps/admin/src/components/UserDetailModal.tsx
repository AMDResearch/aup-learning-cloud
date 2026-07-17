// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

import { useState, useEffect } from 'react';
import { Modal, Spinner, Alert } from 'react-bootstrap';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { getUserDetail } from '@auplc/shared';
import type { UserDetail } from '@auplc/shared';

const PIE_COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444'];

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function pluralize(count: number, singular: string, plural?: string): string {
  return count === 1 ? singular : (plural ?? singular + 's');
}

function formatResourceLabel(resourceType: string, resourceDisplay?: string | null): string {
  if (resourceDisplay && resourceDisplay !== resourceType) {
    return `${resourceDisplay} (${resourceType})`;
  }
  return resourceDisplay ?? resourceType;
}

function formatAcceleratorLabel(acceleratorType?: string | null, acceleratorDisplay?: string | null): string {
  if (acceleratorDisplay && acceleratorDisplay !== acceleratorType) {
    return acceleratorType ? `${acceleratorDisplay} (${acceleratorType})` : acceleratorDisplay;
  }
  return acceleratorDisplay ?? acceleratorType ?? '';
}

interface UserDetailModalProps {
  username: string | null;
  days?: number;
  granularity?: 'day' | 'week';
  onClose: () => void;
}

export function UserDetailModal({ username, days = 30, granularity = 'day', onClose }: UserDetailModalProps) {
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!username) return;
    setLoading(true);
    setError(null);
    setDetail(null);
    getUserDetail(username, days, granularity)
      .then(setDetail)
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, [username, days, granularity]);

  return (
    <Modal show={!!username} onHide={onClose} size="lg" centered>
      <Modal.Header closeButton>
        <Modal.Title>
          <i className="bi bi-person-circle me-2" style={{ color: '#6366f1' }} />
          {username}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {loading && (
          <div className="tw:flex tw:justify-center tw:py-10">
            <Spinner animation="border" variant="primary" />
          </div>
        )}
        {error && <Alert variant="danger">{error}</Alert>}
        {detail && !loading && (
          <>
            {/* Summary row */}
            <div className="tw:flex tw:gap-4 tw:mb-4">
              <div className="bg-body-tertiary tw:flex-1 tw:rounded-lg tw:p-3 tw:text-center">
                <p className="text-body-secondary tw:text-xs tw:mb-1">Total Usage</p>
                <p className="text-body tw:text-xl tw:font-bold tw:mb-0">
                  {formatMinutes(detail.total_minutes)}
                </p>
              </div>
              <div className="bg-body-tertiary tw:flex-1 tw:rounded-lg tw:p-3 tw:text-center">
                <p className="text-body-secondary tw:text-xs tw:mb-1">Sessions</p>
                <p className="text-body tw:text-xl tw:font-bold tw:mb-0">
                  {detail.total_sessions}
                </p>
              </div>
              <div className="bg-body-tertiary tw:flex-1 tw:rounded-lg tw:p-3 tw:text-center">
                <p className="text-body-secondary tw:text-xs tw:mb-1">Avg per Session</p>
                <p className="text-body tw:text-xl tw:font-bold tw:mb-0">
                  {detail.total_sessions > 0
                    ? formatMinutes(Math.round(detail.total_minutes / detail.total_sessions))
                    : '—'}
                </p>
              </div>
            </div>

            {/* Usage chart */}
            {detail.usage.length > 0 ? (
              <div className="tw:mb-4">
                <p className="text-body-secondary tw:text-sm tw:font-semibold tw:mb-2">
                  Usage over time
                </p>
                <ResponsiveContainer width="100%" height={160}>
                  <LineChart data={detail.usage} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--bs-border-color)" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--bs-body-color)' }} tickFormatter={d => d.slice(5)} />
                    <YAxis tick={{ fontSize: 10, fill: 'var(--bs-body-color)' }} />
                    <Tooltip
                      formatter={(v) => [`${v} min`, 'Usage']}
                      contentStyle={{ backgroundColor: 'var(--bs-body-bg)', border: '1px solid var(--bs-border-color)', color: 'var(--bs-body-color)' }}
                    />
                    <Line type="monotone" dataKey="minutes" stroke="#6366f1" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-body-secondary tw:text-sm tw:text-center tw:py-4">No usage data for this period</p>
            )}

            {/* Resource breakdown */}
            {detail.by_resource.length > 0 && (
              <div className="tw:mb-4">
                <p className="text-body-secondary tw:text-sm tw:font-semibold tw:mb-2">
                  By resource
                </p>
                <div className="tw:flex tw:flex-wrap tw:gap-2">
                  {detail.by_resource.map((r, i) => (
                    <span
                      key={r.resource_type}
                      className="tw:rounded-full tw:px-3 tw:py-1 tw:text-xs tw:text-white tw:font-medium"
                      style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                    >
                      {formatResourceLabel(r.resource_type, r.resource_display)} · {formatMinutes(r.minutes)} · {r.sessions} {pluralize(r.sessions, 'session')}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Recent sessions */}
            {detail.recent_sessions.length > 0 && (
              <div>
                <p className="text-body-secondary tw:text-sm tw:font-semibold tw:mb-2">
                  Recent sessions
                </p>
                <div style={{ maxHeight: '220px', overflowY: 'auto' }}>
                  <table className="table table-sm table-hover mb-0">
                    <thead className="tw:sticky tw:top-0">
                      <tr>
                        <th>Resource</th>
                        <th>Start</th>
                        <th>Duration</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.recent_sessions.map((s, i) => {
                        const showResourceCode = Boolean(s.resource_display && s.resource_display !== s.resource_type);
                        const acceleratorLabel = formatAcceleratorLabel(s.accelerator_type, s.accelerator_display);
                        const showAcceleratorCode =
                          Boolean(s.accelerator_display && s.accelerator_type && s.accelerator_display !== s.accelerator_type);
                        return (
                          <tr key={i}>
                          <td>
                            <div>
                              <span>{s.resource_display ?? s.resource_type}</span>
                              {showResourceCode && (
                                <span className="text-body-secondary tw:ms-2 tw:text-xs">
                                  <code>{s.resource_type}</code>
                                </span>
                              )}
                            </div>
                            {acceleratorLabel && (
                              <div className="text-body-secondary tw:text-xs tw:mt-1">
                                {acceleratorLabel}
                                {showAcceleratorCode && (
                                  <span className="tw:ms-2">
                                    <code>{s.accelerator_type}</code>
                                  </span>
                                )}
                              </div>
                            )}
                          </td>
                          <td className="text-body-secondary tw:text-xs">
                            {s.start_time.slice(0, 16).replace('T', ' ')}
                          </td>
                          <td>{s.duration_minutes != null ? formatMinutes(s.duration_minutes) : '—'}</td>
                          <td>
                            <span className={`badge ${s.status === 'completed' || s.status === 'cleaned_up' ? 'bg-success' : 'bg-warning text-dark'}`}>
                              {s.status}
                            </span>
                          </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </Modal.Body>
    </Modal>
  );
}
