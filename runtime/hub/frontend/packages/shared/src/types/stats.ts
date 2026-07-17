// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

export interface DashboardOverview {
  total_users: number;
  active_sessions: number;
  total_usage_minutes: number;
  users_this_week: number;
}

export interface DailyUsage {
  date: string;
  minutes: number;
  sessions: number;
  users: number;
}

export interface ResourceDistribution {
  resource_type: string;
  resource_display?: string;
  minutes: number;
  sessions: number;
  users: number;
  avg_minutes: number;
}

export interface ActiveSession {
  username: string;
  resource_type: string;
  resource_display?: string;
  accelerator_type?: string | null;
  accelerator_display?: string | null;
  start_time: string;
  elapsed_minutes: number;
  idle_warning: boolean;
}

export interface PendingSpawn {
  username: string;
  started: string;
  waiting_minutes: number;
}

export interface TopUser {
  username: string;
  total_minutes: number;
  sessions: number;
}

export interface StatsUsageResponse {
  daily_usage: DailyUsage[];
}

export interface StatsDistributionResponse {
  by_resource: ResourceDistribution[];
  top_users: TopUser[];
}

export interface HourlyUsage {
  hour: number;
  sessions: number;
  minutes: number;
}

export interface UserSession {
  resource_type: string;
  resource_display?: string;
  accelerator_type?: string | null;
  accelerator_display?: string | null;
  start_time: string;
  end_time: string | null;
  duration_minutes: number | null;
  status: string;
}

export interface UserDetail {
  username: string;
  total_minutes: number;
  total_sessions: number;
  usage: DailyUsage[];
  by_resource: ResourceDistribution[];
  recent_sessions: UserSession[];
}
