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

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import type { Resource, Accelerator, GitHubRepo } from '@auplc/shared';
import { validateRepo, fetchGitHubRepos, isCurrentUserGitHub } from '@auplc/shared';
import { CategorySection } from './components/CategorySection';
import { useResources } from './hooks/useResources';
import { useAccelerators } from './hooks/useAccelerators';
import { useQuota } from './hooks/useQuota';

/**
 * Normalize a repo URL typed by the user:
 * - Trims whitespace
 * - Prepends https:// if no protocol is present
 * - Strips /tree/<branch> (GitHub/GitLab style) and returns branch separately
 * - Strips trailing .git suffix
 * Returns { url, branch } where url is the clean clone URL.
 */
function normalizeRepoUrl(raw: string): { url: string; branch: string } {
  let s = raw.trim();
  if (!s) return { url: '', branch: '' };

  if (!s.includes('://')) {
    s = 'https://' + s;
  }

  let branch = '';
  try {
    const parsed = new URL(s);
    let path = parsed.pathname;

    // Strip /tree/<branch> (GitHub: /owner/repo/tree/main)
    const treeMatch = path.match(/^(\/[^/]+\/[^/]+)\/tree\/(.+)$/);
    if (treeMatch) {
      path = treeMatch[1];
      branch = treeMatch[2];
    }

    if (path.endsWith('.git')) {
      path = path.slice(0, -4);
    }

    parsed.pathname = path;
    // Remove any query string or hash that may have been pasted
    parsed.search = '';
    parsed.hash = '';
    return { url: parsed.toString(), branch };
  } catch {
    return { url: s, branch: '' };
  }
}

function validateRepoUrl(url: string, allowedProviders: string[]): string {
  if (!url) return '';
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:') return 'Only HTTPS URLs are supported.';
    const hostname = parsed.hostname.toLowerCase();
    const allowed = allowedProviders.length === 0 || allowedProviders.some(
      p => hostname === p || hostname.endsWith('.' + p)
    );
    if (!allowed) return `Host not allowed. Supported: ${allowedProviders.join(', ')}.`;
  } catch {
    return 'Invalid URL format.';
  }
  return '';
}


function App() {
  const searchParams = new URLSearchParams(window.location.search);
  const initialRepoUrl = searchParams.get('repo_url') ?? '';
  const autostart = searchParams.get('autostart') === '1';
  const initialResourceKey = searchParams.get('resource') ?? '';
  const initialAcceleratorKey = searchParams.get('accelerator') ?? '';

  const { resources, groups, allowedGitProviders, githubAppName, loading: resourcesLoading, error: resourcesError } = useResources();
  const { accelerators, loading: acceleratorsLoading } = useAccelerators();
  const { quota, loading: quotaLoading } = useQuota();

  const autostartFired = useRef(false);

  const [selectedResource, setSelectedResource] = useState<Resource | null>(null);
  const [selectedAcceleratorKey, setSelectedAcceleratorKey] = useState<string | null>(null);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [runtime, setRuntime] = useState(20);
  const [runtimeInput, setRuntimeInput] = useState('20');
  const [repoUrl, setRepoUrl] = useState(initialRepoUrl);
  const [repoUrlError, setRepoUrlError] = useState('');
  const [repoValidating, setRepoValidating] = useState(false);
  const [repoValid, setRepoValid] = useState(false);
  const [paramWarning, setParamWarning] = useState('');
  const validateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [githubRepos, setGithubRepos] = useState<GitHubRepo[]>([]);
  const [githubAppInstalled, setGithubAppInstalled] = useState(false);

  // Derive branch and shareable /hub/git/ link from raw input
  const { branch: repoBranch, url: normalizedRepoUrl } = useMemo(
    () => normalizeRepoUrl(repoUrl),
    [repoUrl]
  );

  const loading = resourcesLoading || acceleratorsLoading || quotaLoading;

  // Validate initial repo_url from query params once providers are loaded
  useEffect(() => {
    if (!initialRepoUrl || allowedGitProviders.length === 0) return;
    const { url } = normalizeRepoUrl(initialRepoUrl);
    const err = validateRepoUrl(url, allowedGitProviders);
    if (err) setRepoUrlError(err);
  }, [allowedGitProviders, initialRepoUrl]);

  // Pre-select resource from query param or autostart default, then auto-submit if needed
  const hasAutoSelected = useRef(false);
  useEffect(() => {
    if (resourcesLoading || resources.length === 0 || hasAutoSelected.current) return;

    let target: Resource | undefined;
    if (initialResourceKey) {
      target = resources.find(r => r.key === initialResourceKey);
      if (!target) {
        setParamWarning(`Unknown resource '${initialResourceKey}', using default.`);
      }
    }
    if (!target && (autostart || initialRepoUrl)) {
      target = resources.find(r => r.metadata?.allowGitClone);
    }
    // Fallback: pre-selection was attempted but failed → select first resource
    if (!target && (initialResourceKey || autostart || initialRepoUrl)) {
      target = resources[0];
    }
    if (target) {
      hasAutoSelected.current = true;
      setSelectedResource(target);
      // Expand the group containing the pre-selected resource
      const targetGroup = groups.find(g => g.resources.some(r => r.key === target!.key));
      if (targetGroup) setExpandedGroup(targetGroup.name);
      if (initialAcceleratorKey) {
        const validKeys = target.metadata?.acceleratorKeys ?? [];
        if (validKeys.includes(initialAcceleratorKey)) {
          setSelectedAcceleratorKey(initialAcceleratorKey);
        } else if (initialAcceleratorKey) {
          setParamWarning(`Unknown accelerator '${initialAcceleratorKey}' for this resource, using default.`);
        }
      }
    } else {
      // Default: expand the first group
      const firstGroup = groups.find(g => g.resources.length > 0);
      if (firstGroup) setExpandedGroup(firstGroup.name);
    }
  }, [resources, groups, resourcesLoading, initialResourceKey, initialAcceleratorKey, autostart, initialRepoUrl]);

  // Auto-submit once resource is selected and form is ready
  useEffect(() => {
    if (!autostart || autostartFired.current) return;
    if (!selectedResource || loading) return;
    autostartFired.current = true;
    // Brief delay to let the DOM settle before submitting
    setTimeout(() => {
      const form = document.getElementById('spawn_form') as HTMLFormElement | null;
      form?.submit();
    }, 300);
  }, [autostart, selectedResource, loading]);

  // Fetch GitHub repos when githubAppName is configured (GitHub OAuth users only)
  const isGitHub = isCurrentUserGitHub();
  useEffect(() => {
    if (!githubAppName || !isGitHub) return;
    fetchGitHubRepos()
      .then(data => {
        setGithubRepos(data.repos);
        setGithubAppInstalled(data.installed);
      })
      .catch(() => {
        // Silently fail - user just won't see repo picker
      });
  }, [githubAppName, isGitHub]);

  // Compute available accelerators based on selected resource
  const availableAccelerators = useMemo(() => {
    if (!selectedResource?.metadata?.acceleratorKeys) {
      return [];
    }
    return accelerators.filter(acc =>
      selectedResource.metadata?.acceleratorKeys?.includes(acc.key)
    );
  }, [selectedResource, accelerators]);

  // Derive selected accelerator: use user selection if valid, otherwise first available
  const selectedAccelerator = useMemo(() => {
    if (availableAccelerators.length === 0) return null;
    const userSelected = availableAccelerators.find(acc => acc.key === selectedAcceleratorKey);
    return userSelected ?? availableAccelerators[0];
  }, [availableAccelerators, selectedAcceleratorKey]);

  const allowGitClone = selectedResource?.metadata?.allowGitClone ?? false;

  const shareableUrl = useMemo(() => {
    if (!selectedResource) return '';
    const params = new URLSearchParams();
    params.set('resource', selectedResource.key);
    if (selectedAccelerator) params.set('accelerator', selectedAccelerator.key);
    if (allowGitClone && normalizedRepoUrl && !repoUrlError) {
      const repoPath = normalizedRepoUrl.replace(/^https?:\/\//, '');
      const branch = repoBranch ? `/tree/${repoBranch}` : '';
      const base = window.location.href.replace(/\/spawn(\/[^?]*)?(\?.*)?$/, '/git/');
      return `${base}${repoPath}${branch}?${params.toString()}`;
    }
    const spawnBase = window.location.href.replace(/\/spawn(\/[^?]*)?(\?.*)?$/, '/spawn');
    return `${spawnBase}?${params.toString()}`;
  }, [normalizedRepoUrl, repoBranch, repoUrlError, allowGitClone, selectedResource, selectedAccelerator]);

  // Memoize quota calculations
  const { cost, canAfford, insufficientQuota, maxRuntime } = useMemo(() => {
    const rate = selectedAccelerator?.quotaRate ?? quota?.rates?.cpu ?? 1;
    const calculatedCost = quota?.enabled ? rate * runtime : 0;
    const balance = quota?.balance ?? 0;

    return {
      cost: calculatedCost,
      canAfford: quota?.unlimited || balance >= calculatedCost,
      insufficientQuota: quota?.enabled && !quota?.unlimited && balance < 10,
      maxRuntime: quota?.enabled && !quota?.unlimited
        ? Math.min(240, Math.floor(balance / rate))
        : 240,
    };
  }, [quota, selectedAccelerator?.quotaRate, runtime]);
  const canStart = selectedResource && canAfford && !repoUrlError && !repoValidating;

  // Memoize non-empty groups filter
  const nonEmptyGroups = useMemo(
    () => groups.filter(g => g.resources.length > 0),
    [groups]
  );

  // Accordion: toggle group, only one open at a time
  const handleToggleGroup = useCallback((groupName: string) => {
    setExpandedGroup(prev => prev === groupName ? null : groupName);
  }, []);

  // Memoize callbacks to prevent child re-renders
  const handleSelectResource = useCallback((resource: Resource) => {
    setSelectedResource(resource);
  }, []);

  const handleClearResource = useCallback(() => {
    setSelectedResource(null);
  }, []);

  const handleRepoUrlChange = useCallback((value: string) => {
    setRepoUrl(value);
    const { url, branch } = normalizeRepoUrl(value);
    const formatError = validateRepoUrl(url, allowedGitProviders);
    setRepoUrlError(formatError);
    setRepoValidating(false);
    setRepoValid(false);

    // Clear pending validation
    if (validateTimerRef.current) clearTimeout(validateTimerRef.current);

    // If format is valid and URL is non-empty, debounce remote validation
    if (!formatError && url) {
      setRepoValidating(true);
      validateTimerRef.current = setTimeout(async () => {
        try {
          const result = await validateRepo(url, branch || undefined);
          if (result.valid) {
            setRepoValid(true);
          } else {
            setRepoUrlError(result.error);
          }
        } catch {
          // API error — don't block the user
        } finally {
          setRepoValidating(false);
        }
      }, 800);
    }
  }, [allowedGitProviders]);

  const handleSelectGitHubRepo = useCallback((repo: GitHubRepo) => {
    const url = repo.html_url;
    setRepoUrl(url);
    const { url: normalizedUrl, branch } = normalizeRepoUrl(url);
    const formatError = validateRepoUrl(normalizedUrl, allowedGitProviders);
    setRepoUrlError(formatError);
    setRepoValid(false);

    if (validateTimerRef.current) clearTimeout(validateTimerRef.current);

    if (!formatError && normalizedUrl) {
      setRepoValidating(true);
      validateTimerRef.current = setTimeout(async () => {
        try {
          const result = await validateRepo(normalizedUrl, branch || undefined);
          if (result.valid) {
            setRepoValid(true);
            setRepoUrlError('');
          } else {
            setRepoUrlError(result.error);
          }
        } catch {
          // API error
        } finally {
          setRepoValidating(false);
        }
      }, 300);
    }
  }, [allowedGitProviders]);

  const handleSelectAccelerator = useCallback((accelerator: Accelerator) => {
    setSelectedAcceleratorKey(accelerator.key);
  }, []);

  const handleRuntimeChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setRuntimeInput(e.target.value);
    const value = parseInt(e.target.value);
    if (!isNaN(value) && value > 0) {
      setRuntime(value);
    }
  }, []);

  const handleRuntimeBlur = useCallback(() => {
    const value = parseInt(runtimeInput);
    const min = 10;
    const max = Math.min(240, maxRuntime);
    if (isNaN(value) || value < min) {
      setRuntime(min);
      setRuntimeInput(String(min));
    } else if (value > max) {
      setRuntime(max);
      setRuntimeInput(String(max));
    } else {
      setRuntime(value);
      setRuntimeInput(String(value));
    }
  }, [runtimeInput, maxRuntime]);

  if (loading) {
    return (
      <div className="loading-spinner">
        <span className="spinner-icon"></span>
        Loading available resources...
      </div>
    );
  }

  if (resourcesError) {
    return (
      <div className="warning-box">
        <strong>Error:</strong> {resourcesError}
      </div>
    );
  }

  return (
    <>
      {/* Hidden inputs for form submission */}
      <input type="hidden" name="resource_type" value={selectedResource?.key ?? ''} />
      {selectedResource && (
        <input
          type="hidden"
          name={`gpu_selection_${selectedResource.key}`}
          value={selectedAccelerator?.key ?? ''}
        />
      )}
      {/* Invalid query param warning */}
      {paramWarning && (
        <div className="warning-box">
          <strong>Warning:</strong> {paramWarning}
        </div>
      )}

      {/* Insufficient quota warning */}
      {insufficientQuota && (
        <div className="warning-box">
          <strong>Insufficient Quota</strong><br />
          You don't have enough quota to start a container. Please contact administrator.
        </div>
      )}

      {/* Resource list */}
      {resources.length === 0 ? (
        <div className="warning-box">
          <strong>No resources available</strong><br />
          Please contact administrator for access.
        </div>
      ) : (
        <>
          <div id="resourceList">
            {nonEmptyGroups.map((group) => (
              <CategorySection
                key={group.name}
                group={group}
                expanded={expandedGroup === group.name}
                onToggle={handleToggleGroup}
                selectedResource={selectedResource}
                onSelectResource={handleSelectResource}
                onClearResource={handleClearResource}
                accelerators={accelerators}
                selectedAccelerator={selectedAccelerator}
                onSelectAccelerator={handleSelectAccelerator}
                repoUrl={repoUrl}
                repoUrlError={repoUrlError}
                repoValidating={repoValidating}
                repoValid={repoValid}
                repoBranch={repoBranch}
                onRepoUrlChange={handleRepoUrlChange}
                allowedGitProviders={allowedGitProviders}
                githubAppName={githubAppName}
                githubRepos={githubRepos}
                githubAppInstalled={githubAppInstalled}
                onSelectGitHubRepo={handleSelectGitHubRepo}
              />
            ))}
          </div>

          {/* Runtime input */}
          <div className="runtime-container">
            <label htmlFor="runtimeInput">Run my server for (minutes):</label>
            <input
              type="number"
              id="runtimeInput"
              name="runtime"
              min={10}
              max={Math.min(240, maxRuntime)}
              step={5}
              value={runtimeInput}
              onChange={handleRuntimeChange}
              onBlur={handleRuntimeBlur}
            />

            {/* Quota cost preview */}
            {quota?.enabled && !quota?.unlimited && (
              <div className="quota-cost-preview">
                <span style={{ color: '#666' }}>Estimated cost: </span>
                <strong style={{ color: canAfford ? '#2e7d32' : '#c62828' }}>{cost}</strong>
                <span style={{ color: '#666' }}> quota (Remaining: </span>
                <strong style={{ color: canAfford ? '#2e7d32' : '#c62828' }}>{(quota?.balance ?? 0) - cost}</strong>
                <span style={{ color: '#666' }}>)</span>
              </div>
            )}
          </div>

          {/* Shareable link - available for all resources */}
          {shareableUrl && (
            <div className="shareable-link">
              <span className="shareable-link-label">Share link:</span>
              <code className="shareable-link-url">{shareableUrl}</code>
              <button
                type="button"
                className="shareable-link-copy"
                onClick={() => navigator.clipboard.writeText(shareableUrl)}
                title="Copy link"
              >
                Copy
              </button>
            </div>
          )}

          {/* Launch section */}
          <div className="launch-section">
            <button
              type="submit"
              className="launch-button"
              disabled={!canStart}
            >
              Launch
            </button>

            {quota?.enabled && (
              <span className="quota-display-simple">
                Quota: <strong style={{ color: quota?.unlimited ? '#28a745' : ((quota?.balance ?? 0) < 10 ? '#dc3545' : '#2c3e50') }}>
                  {quota?.unlimited ? 'Unlimited' : quota?.balance ?? 0}
                </strong>
              </span>
            )}
          </div>
        </>
      )}
    </>
  );
}

export default App;
