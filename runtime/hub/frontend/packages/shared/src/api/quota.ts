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

import type { UserQuota, QuotaRates, UserQuotaInfo } from "../types/quota.js";
import { apiRequest, adminApiRequest } from "./client.js";

export async function getAllQuota(): Promise<{ users: UserQuota[] }> {
  return adminApiRequest<{ users: UserQuota[] }>("/quota");
}

export async function getUserQuota(username: string): Promise<UserQuota> {
  return adminApiRequest<UserQuota>(`/quota/${encodeURIComponent(username)}`);
}

export async function setUserQuota(
  username: string,
  amount: number,
  action: "set" | "add" | "deduct" = "set",
  description?: string
): Promise<UserQuota> {
  return adminApiRequest<UserQuota>(
    `/quota/${encodeURIComponent(username)}`,
    {
      method: "POST",
      body: JSON.stringify({ action, amount, description }),
    }
  );
}

export async function batchSetQuota(
  users: Array<{ username: string; amount: number; unlimited?: boolean }>
): Promise<{ success: number; failed: number }> {
  return adminApiRequest<{ success: number; failed: number }>("/quota/batch", {
    method: "POST",
    body: JSON.stringify({ users }),
  });
}

export async function setUserUnlimited(
  username: string,
  unlimited: boolean
): Promise<UserQuota> {
  return adminApiRequest<UserQuota>(
    `/quota/${encodeURIComponent(username)}`,
    {
      method: "POST",
      body: JSON.stringify({ action: "set_unlimited", unlimited }),
    }
  );
}

export async function getQuotaRates(): Promise<QuotaRates> {
  return apiRequest<QuotaRates>("/quota/rates");
}

export async function getMyQuota(): Promise<UserQuotaInfo> {
  return apiRequest<UserQuotaInfo>("/quota/me");
}
