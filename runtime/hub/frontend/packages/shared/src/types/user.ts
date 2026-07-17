// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

export interface User {
  name: string;
  admin: boolean;
  groups: string[];
  server: string | null;
  pending: string | null;
  last_activity: string | null;
  created: string | null;
  auth_state?: Record<string, unknown>;
  servers?: Record<string, Server>;
}

export interface Server {
  name: string;
  ready: boolean;
  pending: string | null;
  url: string;
  progress_url: string;
  started: string | null;
  last_activity: string | null;
  state: Record<string, unknown>;
  user_options: Record<string, unknown>;
}

export interface UsersResponse {
  items: User[];
  _pagination: {
    offset: number;
    limit: number;
    total: number;
    next: {
      offset: number;
      limit: number;
      url: string;
    } | null;
  };
}

export interface CreateUserRequest {
  usernames: string[];
  admin?: boolean;
}

export interface SetPasswordRequest {
  username: string;
  password: string;
  force_change?: boolean;
}

export interface ProvisionUserEntry {
  username: string;
  password: string;
}

export interface ProvisionUsersRequest {
  users: ProvisionUserEntry[];
  admin?: boolean;
  force_change?: boolean;
  quota?: {
    amount?: number;
    unlimited?: boolean;
  };
}

export interface ProvisionUserResult {
  username: string;
  requested_username: string;
  status: "success" | "failed" | "existed";
  created: boolean;
  password_set: boolean;
  quota_set: boolean;
  error?: string;
}

export interface ProvisionUsersResponse {
  success: number;
  failed: number;
  skipped: number;
  results: ProvisionUserResult[];
}

export interface Group {
  name: string;
  users: string[];
  properties: Record<string, unknown>;
  source?: "github-team" | "system" | "admin";
  resources?: string[];
}
