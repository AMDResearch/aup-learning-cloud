// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

import { apiRequest, adminApiRequest } from "./client.js";
import type {
  DashboardOverview,
  HourlyUsage,
  StatsDistributionResponse,
  StatsUsageResponse,
  UserDetail,
} from "../types/stats.js";

export async function getDashboardOverview(): Promise<DashboardOverview> {
  return adminApiRequest<DashboardOverview>("/stats/overview");
}

export async function getUsageTimeSeries(days = 30, granularity: "day" | "week" = "day"): Promise<StatsUsageResponse> {
  return adminApiRequest<StatsUsageResponse>(`/stats/usage?days=${days}&granularity=${granularity}`);
}

export async function getDistribution(days = 30): Promise<StatsDistributionResponse> {
  return adminApiRequest<StatsDistributionResponse>(`/stats/distribution?days=${days}`);
}

export async function getHourlyDistribution(days = 30, startDate?: string, endDate?: string): Promise<{ hourly: HourlyUsage[] }> {
  const tzOffset = -new Date().getTimezoneOffset(); // minutes ahead of UTC
  const params = new URLSearchParams({
    days: String(days),
    tz_offset: String(tzOffset),
  });
  if (startDate && endDate) {
    params.set("start_date", startDate);
    params.set("end_date", endDate);
  }
  return adminApiRequest(`/stats/hourly?${params.toString()}`);
}

export async function getUserDetail(username: string, days = 30, granularity: "day" | "week" = "day"): Promise<UserDetail> {
  return adminApiRequest<UserDetail>(`/stats/user/${encodeURIComponent(username)}?days=${days}&granularity=${granularity}`);
}

export async function getMyUsage(days = 30, granularity: "day" | "week" = "day"): Promise<UserDetail> {
  return apiRequest<UserDetail>(`/stats/me?days=${days}&granularity=${granularity}`);
}

export function createActiveSessionsSSE(
  onData: (payload: {
    active_sessions: import("../types/stats.js").ActiveSession[];
    pending_spawns: import("../types/stats.js").PendingSpawn[];
  }) => void
): EventSource {
  const base = (window as { jhdata?: { base_url?: string } }).jhdata?.base_url ?? '/hub/';
  const es = new EventSource(`${base}admin/api/stats/active/stream`);
  es.onmessage = (e) => {
    try {
      onData(JSON.parse(e.data));
    } catch { /* ignore parse errors */ }
  };
  return es;
}
