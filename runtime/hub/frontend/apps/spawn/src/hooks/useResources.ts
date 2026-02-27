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

import { useState, useEffect } from 'react';
import type { Resource, ResourceGroup } from '@auplc/shared';
import { getResources } from '@auplc/shared';

// Available resources injected by the spawner
declare global {
  interface Window {
    AVAILABLE_RESOURCES?: string[];
    SINGLE_NODE_MODE?: boolean;
  }
}

interface UseResourcesResult {
  resources: Resource[];
  groups: ResourceGroup[];
  acceleratorKeys: string[];
  allowedGitProviders: string[];
  githubAppName: string;
  loading: boolean;
  error: string | null;
}

export function useResources(): UseResourcesResult {
  const [resources, setResources] = useState<Resource[]>([]);
  const [groups, setGroups] = useState<ResourceGroup[]>([]);
  const [acceleratorKeys, setAcceleratorKeys] = useState<string[]>([]);
  const [allowedGitProviders, setAllowedGitProviders] = useState<string[]>([]);
  const [githubAppName, setGithubAppName] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchResources() {
      try {
        setLoading(true);
        setError(null);

        const response = await getResources();

        // Filter resources based on what the spawner allows
        const allowedKeys = window.AVAILABLE_RESOURCES ?? [];
        const hasFilter = allowedKeys.length > 0;
        const allowedSet = new Set(allowedKeys);

        // If no filter provided or empty, use all resources
        const filteredResources = hasFilter
          ? response.resources.filter(r => allowedSet.has(r.key))
          : response.resources;

        // Filter groups to only include allowed resources
        const filteredGroups = hasFilter
          ? response.groups
              .map(group => ({
                ...group,
                resources: group.resources.filter(r => allowedSet.has(r.key)),
              }))
              .filter(group => group.resources.length > 0)
          : response.groups;

        setResources(filteredResources);
        setGroups(filteredGroups);
        setAcceleratorKeys(response.acceleratorKeys);
        setAllowedGitProviders(response.allowedGitProviders ?? []);
        setGithubAppName(response.githubAppName ?? '');
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load resources');
      } finally {
        setLoading(false);
      }
    }

    fetchResources();
  }, []);

  return { resources, groups, acceleratorKeys, allowedGitProviders, githubAppName, loading, error };
}
