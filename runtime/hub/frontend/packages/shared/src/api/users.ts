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

import type {
  User,
  UsersResponse,
  Group,
  ProvisionUsersRequest,
  ProvisionUsersResponse,
  SetPasswordRequest,
} from "../types/user.js";
import type { HubInfo } from "../types/hub.js";
import { apiRequest, adminApiRequest } from "./client.js";
import { getBaseUrl, getHeaders } from "../utils/xsrf.js";

export interface GetUsersOptions {
  offset?: number;
  limit?: number;
  nameFilter?: string;
  sort?: string;
  state?: string;
}

export async function getHubInfo(): Promise<HubInfo> {
  return apiRequest<HubInfo>("/info");
}

export async function getUsers(
  options: GetUsersOptions = {}
): Promise<UsersResponse> {
  const {
    offset = 0,
    limit = 50,
    nameFilter = "",
    sort = "-last_activity",
    state = "",
  } = options;
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
    include_stopped_servers: "1",
    name_filter: nameFilter,
    sort,
    state,
  });

  const baseUrl = getBaseUrl();
  const url = `${baseUrl}api/users?${params.toString()}`;

  const response = await fetch(url, {
    headers: {
      ...getHeaders(),
      Accept: "application/jupyterhub-pagination+json",
    },
  });

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: response.statusText }));
    throw new Error(error.message || `API Error: ${response.status}`);
  }

  return response.json();
}

export async function getUser(username: string): Promise<User> {
  return apiRequest<User>(`/users/${encodeURIComponent(username)}`);
}

export async function createUser(
  username: string,
  admin = false
): Promise<User> {
  return apiRequest<User>(`/users/${encodeURIComponent(username)}`, {
    method: "POST",
    body: JSON.stringify({ admin }),
  });
}

export async function createUsers(
  usernames: string[],
  admin = false
): Promise<User[]> {
  return apiRequest<User[]>("/users", {
    method: "POST",
    body: JSON.stringify({ usernames, admin }),
  });
}

export async function provisionUsers(
  data: ProvisionUsersRequest
): Promise<ProvisionUsersResponse> {
  return adminApiRequest<ProvisionUsersResponse>("/provision-users", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteUser(username: string): Promise<void> {
  return apiRequest<void>(`/users/${encodeURIComponent(username)}`, {
    method: "DELETE",
  });
}

export async function updateUser(
  username: string,
  data: { admin?: boolean; name?: string; groups?: string[] }
): Promise<User> {
  return apiRequest<User>(`/users/${encodeURIComponent(username)}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function startServer(
  username: string,
  serverName = ""
): Promise<void> {
  const endpoint = serverName
    ? `/users/${encodeURIComponent(username)}/servers/${encodeURIComponent(serverName)}`
    : `/users/${encodeURIComponent(username)}/server`;
  return apiRequest<void>(endpoint, {
    method: "POST",
  });
}

export async function stopServer(
  username: string,
  serverName = ""
): Promise<void> {
  const endpoint = serverName
    ? `/users/${encodeURIComponent(username)}/servers/${encodeURIComponent(serverName)}`
    : `/users/${encodeURIComponent(username)}/server`;
  return apiRequest<void>(endpoint, {
    method: "DELETE",
  });
}

export async function setPassword(
  data: SetPasswordRequest
): Promise<{ message: string }> {
  return adminApiRequest<{ message: string }>("/set-password", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function batchSetPasswords(
  users: Array<{ username: string; password: string }>,
  force_change = true
): Promise<{ success: number; failed: number; results: Array<{ username: string; status: string; error?: string }> }> {
  return adminApiRequest("/batch-set-password", {
    method: "POST",
    body: JSON.stringify({ users, force_change }),
  });
}

export async function generatePassword(): Promise<{ password: string }> {
  return adminApiRequest<{ password: string }>("/generate-password", {
    method: "GET",
  });
}

export interface GroupsResponse {
  groups: Group[];
  github_org: string;
}

export async function getGroups(): Promise<GroupsResponse> {
  return adminApiRequest<GroupsResponse>("/groups");
}

export interface SyncGroupsResponse {
  synced: number;
  failed: number;
  skipped: number;
}

export async function syncGroups(): Promise<SyncGroupsResponse> {
  return adminApiRequest<SyncGroupsResponse>("/groups/sync", {
    method: "POST",
  });
}

export async function getGroup(groupName: string): Promise<Group> {
  return apiRequest<Group>(`/groups/${encodeURIComponent(groupName)}`);
}

export async function createGroup(groupName: string): Promise<Group> {
  return apiRequest<Group>(`/groups/${encodeURIComponent(groupName)}`, {
    method: "POST",
  });
}

export async function deleteGroup(groupName: string): Promise<void> {
  return adminApiRequest<void>(`/groups/${encodeURIComponent(groupName)}`, {
    method: "DELETE",
  });
}

export async function updateGroup(
  groupName: string,
  data: { properties?: Record<string, unknown>; release_protection?: boolean }
): Promise<Group> {
  return adminApiRequest<Group>(`/groups/${encodeURIComponent(groupName)}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function addUserToGroup(
  groupName: string,
  username: string
): Promise<Group> {
  return adminApiRequest<Group>(`/groups/${encodeURIComponent(groupName)}/users`, {
    method: "POST",
    body: JSON.stringify({ users: [username] }),
  });
}

export async function removeUserFromGroup(
  groupName: string,
  username: string
): Promise<Group> {
  return adminApiRequest<Group>(`/groups/${encodeURIComponent(groupName)}/users`, {
    method: "DELETE",
    body: JSON.stringify({ users: [username] }),
  });
}
