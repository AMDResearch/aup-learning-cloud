// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

import { useState, useEffect, useCallback, useRef } from 'react';
import { Spinner, Alert } from 'react-bootstrap';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { UserDetailModal } from '../components/UserDetailModal';
import {
  getDashboardOverview,
  getUsageTimeSeries,
  getDistribution,
  getHourlyDistribution,
  createActiveSessionsSSE,
  stopServer,
} from '@auplc/shared';
import type {
  DashboardOverview,
  DailyUsage,
  ResourceDistribution,
  TopUser,
  ActiveSession,
  PendingSpawn,
  HourlyUsage,
} from '@auplc/shared';

const PIE_COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444'];

type Granularity = 'day' | 'week';

const GRANULARITY_OPTIONS: { label: string; value: Granularity }[] = [
  { label: 'Daily',  value: 'day'  },
  { label: 'Weekly', value: 'week' },
];

function toDateStr(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function daysBetween(start: string, end: string): number {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return Math.max(1, Math.round(ms / 86400000));
}

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

interface StatCardProps {
  title: string;
  value: string | number;
  icon: string;
  color: string;
}

function StatCard({ title, value, icon, color }: StatCardProps) {
  return (
    <div className="bg-body border tw:rounded-xl tw:p-5 tw:shadow-sm tw:flex tw:items-center tw:gap-4">
      <div className={`tw:rounded-lg tw:p-3 ${color}`}>
        <i className={`bi ${icon} tw:text-white tw:text-xl`} />
      </div>
      <div>
        <p className="text-body-secondary tw:text-sm tw:mb-0">{title}</p>
        <p className="text-body tw:text-2xl tw:font-bold tw:mb-0">{value}</p>
      </div>
    </div>
  );
}

function downloadCsv(filename: string, headers: string[], rows: string[][]) {
  const csv = [headers.join(','), ...rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export function Dashboard() {
  const today = toDateStr(new Date());
  const [startDate, setStartDate] = useState(() => toDateStr(new Date(Date.now() - 30 * 86400000)));
  const [endDate, setEndDate] = useState(today);
  const [granularity, setGranularity] = useState<Granularity>('day');
  const days = daysBetween(startDate, endDate);
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [dailyUsage, setDailyUsage] = useState<DailyUsage[]>([]);
  const [byResource, setByResource] = useState<ResourceDistribution[]>([]);
  const [topUsers, setTopUsers] = useState<TopUser[]>([]);
  const [hourlyUsage, setHourlyUsage] = useState<HourlyUsage[]>([]);
  const [activeSessions, setActiveSessions] = useState<ActiveSession[]>([]);
  const [pendingSpawns, setPendingSpawns] = useState<PendingSpawn[]>([]);
  const [loading, setLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedUser, setSelectedUser] = useState<string | null>(null);

  // SSE: live active sessions + pending spawns
  useEffect(() => {
    const es = createActiveSessionsSSE(({ active_sessions, pending_spawns }) => {
      setActiveSessions(active_sessions);
      setPendingSpawns(pending_spawns);
    });
    return () => es.close();
  }, []);

  // Load overview + distribution + initial chart when date range changes
  const loadAll = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [ov, usage, dist, hourly] = await Promise.all([
        getDashboardOverview(),
        getUsageTimeSeries(days, granularity),
        getDistribution(days),
        getHourlyDistribution(days, startDate, endDate),
      ]);
      setOverview(ov);
      setDailyUsage(usage.daily_usage);
      setByResource(dist.by_resource);
      setTopUsers(dist.top_users);
      setHourlyUsage(hourly.hourly);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, [days, startDate, endDate]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load only time series when granularity changes (skip on initial mount, loadAll handles it)
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return; }
    setChartLoading(true);
    getUsageTimeSeries(days, granularity)
      .then(u => setDailyUsage(u.daily_usage))
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load chart data'))
      .finally(() => setChartLoading(false));
  }, [granularity]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { loadAll(); }, [loadAll]);

  return (
    <div>
      {/* Header row */}
      <div className="tw:flex tw:items-center tw:justify-between tw:mb-6 tw:flex-wrap tw:gap-2">
        <h4 className="text-body tw:font-semibold tw:mb-0">Usage Dashboard</h4>
        <div className="tw:flex tw:items-center tw:gap-1">
          <input
            type="date"
            className="form-control form-control-sm"
            value={startDate}
            max={endDate}
            onChange={e => setStartDate(e.target.value)}
          />
          <span className="text-body-secondary tw:text-sm">—</span>
          <input
            type="date"
            className="form-control form-control-sm"
            value={endDate}
            min={startDate}
            max={today}
            onChange={e => setEndDate(e.target.value)}
          />
          <button
            className="btn btn-outline-secondary btn-sm tw:ml-2"
            title="Export CSV"
            onClick={() => {
              if (dailyUsage.length > 0) {
                downloadCsv(`usage-${startDate}-${endDate}.csv`,
                  ['Date', 'Minutes', 'Active Users'],
                  dailyUsage.map(d => [d.date, String(d.minutes), String(d.users)]));
              }
            }}
            disabled={dailyUsage.length === 0}
          >
            <i className="bi bi-download tw:mr-1" /> Export
          </button>
        </div>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {loading ? (
        <div className="tw:flex tw:justify-center tw:py-20">
          <Spinner animation="border" variant="primary" />
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="tw:grid tw:grid-cols-2 tw:gap-4 tw:mb-6 md:tw:grid-cols-4">
            <StatCard
              title="Total Users"
              value={overview?.total_users ?? 0}
              icon="bi-people-fill"
              color="tw:bg-indigo-500"
            />
            <StatCard
              title="Active Sessions"
              value={overview?.active_sessions ?? 0}
              icon="bi-play-circle-fill"
              color="tw:bg-emerald-500"
            />
            <StatCard
              title="Total Usage"
              value={formatMinutes(overview?.total_usage_minutes ?? 0)}
              icon="bi-clock-history"
              color="tw:bg-violet-500"
            />
            <StatCard
              title="Active This Week"
              value={overview?.users_this_week ?? 0}
              icon="bi-activity"
              color="tw:bg-pink-500"
            />
          </div>

          {/* Active Now + Pending Spawns */}
          <div className="tw:grid tw:grid-cols-1 tw:gap-4 tw:mb-4 lg:tw:grid-cols-3">
            {/* Active Now */}
            <div className="bg-body border tw:rounded-xl tw:shadow-sm tw:p-5 lg:tw:col-span-2">
              <div className="tw:flex tw:items-center tw:gap-2 tw:mb-3">
                <h6 className="text-body-secondary tw:font-semibold tw:mb-0">Active Now</h6>
                <span className="tw:inline-flex tw:items-center tw:gap-1 tw:text-xs tw:text-emerald-600 tw:font-medium">
                  <span className="tw:inline-block tw:w-2 tw:h-2 tw:rounded-full tw:bg-emerald-500 tw:animate-pulse" />
                  Live
                </span>
                <span className="badge bg-secondary tw:ml-auto">{activeSessions.length}</span>
              </div>
              {activeSessions.length === 0 ? (
                <p className="text-body-secondary tw:text-sm tw:text-center tw:py-4">No active sessions</p>
              ) : (
                <table className="table table-sm table-hover mb-0">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Course</th>
                      <th>Started</th>
                      <th>Elapsed</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeSessions.map((s, i) => {
                      const showResourceCode = Boolean(s.resource_display && s.resource_display !== s.resource_type);
                      const acceleratorLabel = formatAcceleratorLabel(s.accelerator_type, s.accelerator_display);
                      const showAcceleratorCode =
                        Boolean(s.accelerator_display && s.accelerator_type && s.accelerator_display !== s.accelerator_type);
                      return (
                        <tr key={i} className={s.idle_warning ? 'table-warning' : ''}>
                          <td style={{ cursor: 'pointer' }} onClick={() => setSelectedUser(s.username)}>
                            <span className="tw:text-indigo-600 tw:font-medium">
                              <i className="bi bi-person me-1" />{s.username}
                            </span>
                          </td>
                          <td>
                            <div>
                              <span>{formatResourceLabel(s.resource_type, s.resource_display)}</span>
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
                            {new Date(s.start_time + 'Z').toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                          </td>
                          <td>
                            {s.idle_warning && <i className="bi bi-exclamation-triangle-fill text-warning me-1" title="Possibly idle" />}
                            {formatMinutes(s.elapsed_minutes)}
                          </td>
                          <td>
                            <button
                              className="btn btn-outline-danger btn-sm tw:py-0"
                              title="Stop server"
                              onClick={() => stopServer(s.username).catch(() => {})}
                            >
                              <i className="bi bi-stop-fill" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            {/* Pending Spawns */}
            <div className="bg-body border tw:rounded-xl tw:shadow-sm tw:p-5">
              <div className="tw:flex tw:items-center tw:gap-2 tw:mb-3">
                <h6 className="text-body-secondary tw:font-semibold tw:mb-0">Spawning</h6>
                <span className="tw:inline-flex tw:items-center tw:gap-1 tw:text-xs tw:text-amber-600 tw:font-medium">
                  <span className="tw:inline-block tw:w-2 tw:h-2 tw:rounded-full tw:bg-amber-500 tw:animate-pulse" />
                  Live
                </span>
                <span className="badge bg-secondary tw:ml-auto">{pendingSpawns.length}</span>
              </div>
              {pendingSpawns.length === 0 ? (
                <p className="text-body-secondary tw:text-sm tw:text-center tw:py-4">No pending spawns</p>
              ) : (
                <div className="tw:flex tw:flex-col tw:gap-2">
                  {pendingSpawns.map((p, i) => (
                    <div key={i} className="tw:flex tw:items-center tw:justify-between tw:text-sm">
                      <span className="text-body">
                        <i className="bi bi-hourglass-split text-warning me-1" />
                        {p.username}
                      </span>
                      <span className="text-body-secondary tw:text-xs">{formatMinutes(p.waiting_minutes)} waiting</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Usage trend — full width */}
          <div className="bg-body border tw:rounded-xl tw:shadow-sm tw:p-5 tw:mb-4">
            <div className="tw:flex tw:items-center tw:justify-between tw:mb-4">
              <h6 className="text-body-secondary tw:font-semibold tw:mb-0">Usage (minutes)</h6>
              <div className="bg-body-tertiary tw:flex tw:gap-1 tw:rounded-lg tw:p-1">
                {GRANULARITY_OPTIONS.map((g) => (
                  <button
                    key={g.value}
                    onClick={() => setGranularity(g.value)}
                    className={`tw:px-3 tw:py-1 tw:rounded-md tw:text-sm tw:font-medium tw:transition-all tw:border-0 tw:cursor-pointer ${
                      granularity === g.value
                        ? 'bg-body tw:shadow-sm tw:text-indigo-600'
                        : 'tw:bg-transparent text-body-secondary'
                    }`}
                  >
                    {g.label}
                  </button>
                ))}
              </div>
            </div>
            {chartLoading ? (
              <div className="tw:flex tw:justify-center tw:py-10"><Spinner animation="border" size="sm" variant="primary" /></div>
            ) : dailyUsage.length === 0 ? (
              <p className="text-body-secondary tw:text-sm tw:text-center tw:py-10">No data for this period</p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={dailyUsage} margin={{ top: 4, right: 40, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--bs-border-color)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--bs-body-color)' }} tickFormatter={d => d.slice(5)} />
                  <YAxis yAxisId="minutes" tick={{ fontSize: 11, fill: 'var(--bs-body-color)' }} />
                  <YAxis yAxisId="users" orientation="right" tick={{ fontSize: 11, fill: 'var(--bs-body-color)' }} />
                  <Tooltip
                    formatter={(v, name) => name === 'Minutes' ? [`${v} min`, name] : [v, name]}
                    contentStyle={{ backgroundColor: 'var(--bs-body-bg)', border: '1px solid var(--bs-border-color)', color: 'var(--bs-body-color)' }}
                  />
                  <Legend />
                  <Line yAxisId="minutes" type="monotone" dataKey="minutes" stroke="#6366f1" strokeWidth={2} dot={false} name="Minutes" />
                  <Line yAxisId="users" type="monotone" dataKey="users" stroke="#10b981" strokeWidth={2} dot={false} name="Active Users" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Hourly usage distribution — full width */}
          <div className="bg-body border tw:rounded-xl tw:shadow-sm tw:p-5 tw:mb-4">
            <h6 className="text-body-secondary tw:font-semibold tw:mb-4">
              <i className="bi bi-clock me-2" />Sessions by Hour of Day
            </h6>
            {hourlyUsage.every(h => h.sessions === 0) ? (
              <p className="text-body-secondary tw:text-sm tw:text-center tw:py-10">No data for this period</p>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={hourlyUsage} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--bs-border-color)" />
                  <XAxis dataKey="hour" tick={{ fontSize: 11, fill: 'var(--bs-body-color)' }} tickFormatter={h => `${h}:00`} interval={2} />
                  <YAxis tick={{ fontSize: 11, fill: 'var(--bs-body-color)' }} allowDecimals={false} />
                  <Tooltip
                    formatter={(v, name) => [v, name === 'sessions' ? 'Sessions' : name]}
                    labelFormatter={h => `${h}:00 – ${h}:59`}
                    contentStyle={{ backgroundColor: 'var(--bs-body-bg)', border: '1px solid var(--bs-border-color)', color: 'var(--bs-body-color)' }}
                  />
                  <Bar dataKey="sessions" fill="#8b5cf6" name="sessions" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Course stats + Top users — two columns */}
          <div className="tw:grid tw:grid-cols-1 tw:gap-4 lg:tw:grid-cols-2">
            {/* Course ranking */}
            <div className="bg-body border tw:rounded-xl tw:shadow-sm tw:p-5">
              <h6 className="text-body-secondary tw:font-semibold tw:mb-4">
                <i className="bi bi-journal-code me-2" />Course Usage
              </h6>
              {byResource.length === 0 ? (
                <p className="text-body-secondary tw:text-sm tw:text-center tw:py-6">No data for this period</p>
              ) : (() => {
                const maxMin = Math.max(...byResource.map(r => r.minutes));
                return (
                  <div className="tw:flex tw:flex-col tw:gap-3">
                    {byResource.map((r, i) => (
                      <div key={r.resource_type}>
                        <div className="tw:flex tw:justify-between tw:items-baseline tw:mb-1">
                          <span className="tw:flex tw:items-center tw:gap-2 tw:text-sm text-body">
                            <span
                              className="tw:inline-block tw:w-2 tw:h-2 tw:rounded-full tw:shrink-0"
                              style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                            />
                            {formatResourceLabel(r.resource_type, r.resource_display)}
                          </span>
                          <span className="text-body-secondary tw:text-xs tw:shrink-0 tw:ml-2">
                            {formatMinutes(r.minutes)} · {r.sessions} {pluralize(r.sessions, 'session')} · avg {formatMinutes(Math.round(r.avg_minutes))}
                          </span>
                        </div>
                        <div className="tw:w-full tw:rounded-full tw:h-1.5 bg-body-tertiary">
                          <div
                            className="tw:h-1.5 tw:rounded-full tw:transition-all"
                            style={{
                              width: `${(r.minutes / maxMin) * 100}%`,
                              backgroundColor: PIE_COLORS[i % PIE_COLORS.length],
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>

            {/* Top users */}
            <div className="bg-body border tw:rounded-xl tw:shadow-sm tw:p-5">
              <h6 className="text-body-secondary tw:font-semibold tw:mb-4">
                <i className="bi bi-trophy me-2" />Top Users
              </h6>
              {topUsers.length === 0 ? (
                <p className="text-body-secondary tw:text-sm tw:text-center tw:py-6">No data for this period</p>
              ) : (
                <table className="table table-sm table-hover mb-0">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Username</th>
                      <th>Total Usage</th>
                      <th>Sessions</th>
                      <th>Avg</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topUsers.map((u, i) => (
                      <tr
                        key={u.username}
                        style={{ cursor: 'pointer' }}
                        onClick={() => setSelectedUser(u.username)}
                      >
                        <td className="text-body-secondary">{i + 1}</td>
                        <td>
                          <span className="tw:text-indigo-600 tw:font-medium tw:hover:underline">
                            <i className="bi bi-person me-1" />{u.username}
                          </span>
                        </td>
                        <td>{formatMinutes(u.total_minutes)}</td>
                        <td>{u.sessions}</td>
                        <td>{formatMinutes(Math.round(u.total_minutes / u.sessions))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}

      {/* Per-user detail modal */}
      <UserDetailModal
        username={selectedUser}
        days={days}
        granularity={granularity}
        onClose={() => setSelectedUser(null)}
      />
    </div>
  );
}
