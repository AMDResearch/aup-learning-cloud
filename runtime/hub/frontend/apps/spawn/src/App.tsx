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
import { validateRepo, fetchGitHubRepos, isCurrentUserGitHub, PLATFORM_NAME, fetchPlatformInfo } from '@auplc/shared';

type Theme = 'light' | 'dark';
function getInitialTheme(): Theme {
  const stored =
    (localStorage.getItem('auplc-theme') as Theme | null) ??
    (localStorage.getItem('jupyterhub-bs-theme') as Theme | null);
  if (stored === 'light' || stored === 'dark') return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
function applyTheme(t: Theme) {
  document.documentElement.setAttribute('data-bs-theme', t);
  localStorage.setItem('auplc-theme', t);
  localStorage.setItem('jupyterhub-bs-theme', t);
}
applyTheme(getInitialTheme());
import { CategorySection } from './components/CategorySection';
import { useResources } from './hooks/useResources';
import { useAccelerators } from './hooks/useAccelerators';
import { useQuota } from './hooks/useQuota';

function normalizeRepoUrl(raw: string): { url: string; branch: string } {
  let s = raw.trim();
  if (!s) return { url: '', branch: '' };
  if (!s.includes('://')) s = 'https://' + s;
  let branch = '';
  try {
    const parsed = new URL(s);
    let path = parsed.pathname;
    const treeMatch = path.match(/^(\/[^/]+\/[^/]+)\/tree\/(.+)$/);
    if (treeMatch) { path = treeMatch[1]; branch = treeMatch[2]; }
    if (path.endsWith('.git')) path = path.slice(0, -4);
    parsed.pathname = path;
    parsed.search = '';
    parsed.hash = '';
    return { url: parsed.toString(), branch };
  } catch { return { url: s, branch: '' }; }
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
  } catch { return 'Invalid URL format.'; }
  return '';
}


function App() {
  const searchParams = new URLSearchParams(window.location.search);
  const initialRepoUrl = searchParams.get('repo_url') ?? '';
  const autostart = searchParams.get('autostart') === '1';
  const initialResourceKey = searchParams.get('resource') ?? '';
  const initialAcceleratorKey = searchParams.get('accelerator') ?? '';

  const {
    resources,
    groups,
    allowedGitProviders,
    githubAppName,
    allowPersistenceChoice,
    defaultPersistence,
    loading: resourcesLoading,
    error: resourcesError,
  } = useResources();
  const { accelerators, loading: acceleratorsLoading } = useAccelerators();
  const { quota, loading: quotaLoading } = useQuota();

  const autostartFired = useRef(false);

  const [selectedResource, setSelectedResource] = useState<Resource | null>(null);
  const [selectedAcceleratorKey, setSelectedAcceleratorKey] = useState<string | null>(null);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [runtime, setRuntime] = useState(20);
  const [runtimeInput, setRuntimeInput] = useState('20');
  const [platformName, setPlatformName] = useState<string>(PLATFORM_NAME);
  const [repoUrl, setRepoUrl] = useState(initialRepoUrl);
  const [repoPersist, setRepoPersist] = useState<boolean | null>(null);
  const [repoUrlError, setRepoUrlError] = useState('');
  const [repoValidating, setRepoValidating] = useState(false);
  const [repoValid, setRepoValid] = useState(false);
  const [paramWarning, setParamWarning] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [favorites, setFavorites] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem('auplc-favorites');
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch { return new Set(); }
  });
  const validateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const toggleTheme = useCallback(() => {
    setTheme(t => { const n = t === 'light' ? 'dark' : 'light'; applyTheme(n); return n; });
  }, []);
  const [githubRepos, setGithubRepos] = useState<GitHubRepo[]>([]);
  const [githubAppInstalled, setGithubAppInstalled] = useState(false);

  const { branch: repoBranch, url: normalizedRepoUrl } = useMemo(
    () => normalizeRepoUrl(repoUrl), [repoUrl]
  );

  const loading = resourcesLoading || acceleratorsLoading || quotaLoading;

  useEffect(() => {
    fetchPlatformInfo().then(info => setPlatformName(info.platform)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!initialRepoUrl || allowedGitProviders.length === 0) return;
    const { url } = normalizeRepoUrl(initialRepoUrl);
    const err = validateRepoUrl(url, allowedGitProviders);
    if (err) setRepoUrlError(err);
  }, [allowedGitProviders, initialRepoUrl]);

  const hasAutoSelected = useRef(false);
  useEffect(() => {
    if (resourcesLoading || resources.length === 0 || hasAutoSelected.current) return;
    let target: Resource | undefined;
    if (initialResourceKey) {
      target = resources.find(r => r.key === initialResourceKey);
      if (!target) setParamWarning(`Unknown resource '${initialResourceKey}', using default.`);
    }
    if (!target && (autostart || initialRepoUrl)) target = resources.find(r => r.metadata?.allowGitClone);
    if (!target && (initialResourceKey || autostart || initialRepoUrl)) target = resources[0];
    if (target) {
      hasAutoSelected.current = true;
      setSelectedResource(target);
      const targetGroup = groups.find(g => g.resources.some(r => r.key === target!.key));
      if (targetGroup) setExpandedGroup(targetGroup.name);
      if (initialAcceleratorKey) {
        const validKeys = target.metadata?.acceleratorKeys ?? [];
        if (validKeys.includes(initialAcceleratorKey)) setSelectedAcceleratorKey(initialAcceleratorKey);
        else if (initialAcceleratorKey) setParamWarning(`Unknown accelerator '${initialAcceleratorKey}' for this resource, using default.`);
      }
    } else {
      const firstGroup = groups.find(g => g.resources.length > 0);
      if (firstGroup) setExpandedGroup(firstGroup.name);
    }
  }, [resources, groups, resourcesLoading, initialResourceKey, initialAcceleratorKey, autostart, initialRepoUrl]);

  useEffect(() => {
    if (!autostart || autostartFired.current) return;
    if (!selectedResource || loading) return;
    autostartFired.current = true;
    setTimeout(() => {
      const form = document.getElementById('spawn_form') as HTMLFormElement | null;
      form?.submit();
    }, 300);
  }, [autostart, selectedResource, loading]);

  const isGitHub = isCurrentUserGitHub();
  useEffect(() => {
    if (!githubAppName || !isGitHub) return;
    fetchGitHubRepos()
      .then(data => { setGithubRepos(data.repos); setGithubAppInstalled(data.installed); })
      .catch(() => {});
  }, [githubAppName, isGitHub]);

  const availableAccelerators = useMemo(() => {
    if (!selectedResource?.metadata?.acceleratorKeys) return [];
    return accelerators.filter(acc => selectedResource.metadata?.acceleratorKeys?.includes(acc.key));
  }, [selectedResource, accelerators]);

  const selectedAccelerator = useMemo(() => {
    if (availableAccelerators.length === 0) return null;
    const userSelected = availableAccelerators.find(acc => acc.key === selectedAcceleratorKey);
    return userSelected ?? availableAccelerators[0];
  }, [availableAccelerators, selectedAcceleratorKey]);

  const allowGitClone = selectedResource?.metadata?.allowGitClone ?? false;
  const repoPersistValue = repoPersist ?? defaultPersistence;
  const showRepoPersistenceChoice = Boolean(selectedResource && allowGitClone && allowPersistenceChoice);

  useEffect(() => {
    setRepoPersist(defaultPersistence);
  }, [defaultPersistence]);

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

  const { cost, canAfford, insufficientQuota, maxRuntime } = useMemo(() => {
    const rate = selectedAccelerator?.quotaRate ?? quota?.rates?.cpu ?? 1;
    const calculatedCost = quota?.enabled ? rate * runtime : 0;
    const balance = quota?.balance ?? 0;
    return {
      cost: calculatedCost,
      canAfford: quota?.unlimited || balance >= calculatedCost,
      insufficientQuota: quota?.enabled && !quota?.unlimited && balance < 10,
      maxRuntime: quota?.enabled && !quota?.unlimited ? Math.min(240, Math.floor(balance / rate)) : 240,
    };
  }, [quota, selectedAccelerator?.quotaRate, runtime]);
  const canStart = selectedResource && canAfford && !repoUrlError && !repoValidating;

  const toggleFavorite = useCallback((key: string) => {
    setFavorites(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      localStorage.setItem('auplc-favorites', JSON.stringify([...next]));
      return next;
    });
  }, []);

  const favoritesGroup = useMemo(() => {
    if (favorites.size === 0) return null;
    const favResources = resources.filter(r => favorites.has(r.key));
    if (favResources.length === 0) return null;
    return { name: '__favorites__', displayName: '⭐ Favorites', resources: favResources };
  }, [favorites, resources]);

  const filteredGroups = useMemo(() => {
    if (!searchQuery.trim()) return groups.filter(g => g.resources.length > 0);
    const q = searchQuery.toLowerCase();
    return groups
      .map(g => ({
        ...g,
        resources: g.resources.filter(r =>
          r.key.toLowerCase().includes(q) ||
          (r.metadata?.description ?? '').toLowerCase().includes(q) ||
          (r.metadata?.subDescription ?? '').toLowerCase().includes(q)
        ),
      }))
      .filter(g => g.resources.length > 0);
  }, [groups, searchQuery]);
  const totalResources = resources.length;

  const handleToggleGroup = useCallback((groupName: string) => {
    setExpandedGroup(prev => prev === groupName ? null : groupName);
  }, []);

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
    if (validateTimerRef.current) clearTimeout(validateTimerRef.current);
    if (!formatError && url) {
      setRepoValidating(true);
      validateTimerRef.current = setTimeout(async () => {
        try {
          const result = await validateRepo(url, branch || undefined);
          if (result.valid) setRepoValid(true);
          else setRepoUrlError(result.error);
        } catch { /* API error */ }
        finally { setRepoValidating(false); }
      }, 800);
    }
  }, [allowedGitProviders]);

  const handleSelectGitHubRepo = useCallback((repo: GitHubRepo) => {
    const url = repo.html_url;
    setRepoUrl(url);
    const { url: nUrl, branch } = normalizeRepoUrl(url);
    const formatError = validateRepoUrl(nUrl, allowedGitProviders);
    setRepoUrlError(formatError);
    setRepoValid(false);
    if (validateTimerRef.current) clearTimeout(validateTimerRef.current);
    if (!formatError && nUrl) {
      setRepoValidating(true);
      validateTimerRef.current = setTimeout(async () => {
        try {
          const result = await validateRepo(nUrl, branch || undefined);
          if (result.valid) { setRepoValid(true); setRepoUrlError(''); }
          else setRepoUrlError(result.error);
        } catch { /* API error */ }
        finally { setRepoValidating(false); }
      }, 300);
    }
  }, [allowedGitProviders]);

  const handleSelectAccelerator = useCallback((accelerator: Accelerator) => {
    setSelectedAcceleratorKey(accelerator.key);
  }, []);

  const handleRuntimeChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setRuntimeInput(e.target.value);
    const value = parseInt(e.target.value);
    if (!isNaN(value) && value > 0) setRuntime(value);
  }, []);

  const handleRuntimeBlur = useCallback(() => {
    const value = parseInt(runtimeInput);
    const min = 10;
    const max = Math.min(240, maxRuntime);
    if (isNaN(value) || value < min) { setRuntime(min); setRuntimeInput(String(min)); }
    else if (value > max) { setRuntime(max); setRuntimeInput(String(max)); }
    else { setRuntime(value); setRuntimeInput(String(value)); }
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
    return <div className="warning-box"><strong>Error:</strong> {resourcesError}</div>;
  }

  const homeUrl = `${window.jhdata?.base_url ?? '/hub/'}home`;
  const acceleratorType = selectedResource?.metadata?.accelerator ?? 'GPU';

  return (
    <>
      {/* Hidden form inputs */}
      <input type="hidden" name="resource_type" value={selectedResource?.key ?? ''} />
      {selectedResource && (
        <input type="hidden" name={`gpu_selection_${selectedResource.key}`} value={selectedAccelerator?.key ?? ''} />
      )}
      {allowGitClone && <input type="hidden" name="repo_url" value={repoUrl} />}
      {allowGitClone && <input type="hidden" name="repo_persist" value={repoPersistValue ? 'true' : 'false'} />}

      {/* Page header */}
      <div className="spawn-header">
        <div className="spawn-breadcrumb">
          <a href={homeUrl}>Home</a>
          <span>/</span>
          <span>Launch Server</span>
          <button type="button" className="spawn-theme-toggle" onClick={toggleTheme} title={theme === 'light' ? 'Dark mode' : 'Light mode'}>
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
        </div>
        <h1>Launch Your Server</h1>
        <p>Select a resource, configure your environment, and launch on {platformName}</p>
      </div>

      {/* Warnings */}
      {paramWarning && <div className="warning-box"><strong>Warning:</strong> {paramWarning}</div>}
      {insufficientQuota && (
        <div className="warning-box">
          <strong>Insufficient Quota</strong><br />
          You don't have enough quota to start a container. Please contact administrator.
        </div>
      )}

      {resources.length === 0 ? (
        <div className="warning-box">
          <strong>No resources available</strong><br />
          Please contact administrator for access.
        </div>
      ) : (
        <div className="spawn-layout">
          {/* LEFT: Resource picker */}
          <div className="spawn-picker">
            <div className="picker-header">
              <h2>Choose a Resource</h2>
              <span className="picker-count">{totalResources} {totalResources === 1 ? 'resource' : 'resources'}</span>
            </div>
            <div className="picker-search">
              <input
                type="text"
                className="sidebar-git-input"
                placeholder="Search resources..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="picker-body">
              {favoritesGroup && !searchQuery && (
                <CategorySection
                  key="__favorites__"
                  group={favoritesGroup}
                  expanded={expandedGroup === '__favorites__'}
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
                  favorites={favorites}
                  onToggleFavorite={toggleFavorite}
                />
              )}
              {filteredGroups.map((group) => (
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
                  favorites={favorites}
                  onToggleFavorite={toggleFavorite}
                />
              ))}
            </div>
          </div>

          {/* RIGHT: Configuration sidebar */}
          <aside className="spawn-sidebar">
            <div className="sidebar-panel">
              <div className="sidebar-panel-title">Configuration</div>

              {!selectedResource && (
                <div className="sidebar-empty">Select a resource to configure</div>
              )}

              {/* GPU selection */}
              {selectedResource && availableAccelerators.length > 0 && (
                <div className="sidebar-section">
                  <div className="sidebar-label">
                    {acceleratorType} Node
                  </div>
                  <div className="sidebar-gpu-list">
                    {availableAccelerators.map(acc => (
                      <div
                        key={acc.key}
                        className={`sidebar-gpu-card ${selectedAccelerator?.key === acc.key ? 'selected' : ''}`}
                        onClick={() => handleSelectAccelerator(acc)}
                      >
                        <input
                          type="radio"
                          className="sidebar-gpu-radio"
                          checked={selectedAccelerator?.key === acc.key}
                          onChange={() => handleSelectAccelerator(acc)}
                        />
                        <div>
                          <div className="sidebar-gpu-name">{acc.displayName}</div>
                          <div className="sidebar-gpu-desc">{acc.description}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Git repo input */}
              {selectedResource && allowGitClone && (
                <div className="sidebar-section">
                  <div className="sidebar-label">
                    Git Repository <span className="sidebar-optional">(optional)</span>
                  </div>
                  <input
                    type="text"
                    className={`sidebar-git-input ${repoUrlError ? 'input-error' : ''} ${repoValid ? 'input-valid' : ''}`}
                    value={repoUrl}
                    onChange={e => handleRepoUrlChange(e.target.value)}
                    placeholder="https://github.com/owner/repo"
                    autoComplete="off"
                    spellCheck={false}
                  />
                  {repoValidating && <small className="sidebar-git-status loading">Checking repository...</small>}
                  {repoValid && !repoValidating && (
                    <small className="sidebar-git-status success">
                      &#x2713; Repository verified{repoBranch ? ` · Branch: ${repoBranch}` : ''}
                    </small>
                  )}
                  {repoUrlError && !repoValidating && <small className="sidebar-git-status error">{repoUrlError}</small>}
                  {showRepoPersistenceChoice && (
                    <label className="sidebar-runtime-row">
                      <input
                        type="checkbox"
                        className="sidebar-gpu-radio"
                        checked={repoPersistValue}
                        onChange={e => setRepoPersist(e.target.checked)}
                      />
                      <span className="sidebar-label">Keep this repository after the server stops</span>
                    </label>
                  )}
                  {showRepoPersistenceChoice && (
                    <small className="sidebar-git-status">
                      If enabled, an existing repository folder will be reused and not overwritten.
                    </small>
                  )}
                  {githubAppName && isGitHub && (
                    <a
                      className="sidebar-github-link"
                      href={`https://github.com/apps/${githubAppName}/installations/new`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {githubAppInstalled ? 'Add access to more repositories' : 'Authorize private repo access'}
                    </a>
                  )}
                </div>
              )}

              {/* Runtime */}
              {selectedResource && (
                <div className="sidebar-section">
                  <div className="sidebar-label">Runtime</div>
                  <div className="sidebar-runtime-row">
                    <input
                      type="number"
                      name="runtime"
                      className="sidebar-runtime-input"
                      min={10}
                      max={Math.min(240, maxRuntime)}
                      step={5}
                      value={runtimeInput}
                      onChange={handleRuntimeChange}
                      onBlur={handleRuntimeBlur}
                    />
                    <span className="sidebar-runtime-unit">minutes</span>
                  </div>
                  {quota?.enabled && !quota?.unlimited && (
                    <div className="sidebar-quota-preview">
                      Est. cost: <strong style={{ color: canAfford ? '#2e7d32' : '#c62828' }}>{cost}</strong>
                      {' · '}Remaining: <strong style={{ color: canAfford ? '#2e7d32' : '#c62828' }}>{(quota?.balance ?? 0) - cost}</strong>
                      <span className="quota-rate-tip" title={
                        `Rate: ${selectedAccelerator?.quotaRate ?? quota?.rates?.cpu ?? 1} credits/min` +
                        (selectedAccelerator ? ` (${selectedAccelerator.displayName})` : ' (CPU)') +
                        `\nCost = rate × ${runtime} min = ${cost} credits`
                      }>?</span>
                    </div>
                  )}
                </div>
              )}

              {/* Quota warning */}
              {quota?.enabled && !quota?.unlimited && !canAfford && selectedResource && (
                <div className="sidebar-quota-warning">
                  <strong>Insufficient Quota</strong> — You need {cost} credits but only have {quota?.balance ?? 0}. Reduce runtime or contact an administrator.
                </div>
              )}

              {/* Launch button */}
              <button type="submit" className="sidebar-launch-btn" disabled={!canStart}>
                Launch Server
              </button>

              {quota?.enabled && (
                <div className="sidebar-quota-display">
                  Quota:{' '}
                  <strong style={{ color: quota?.unlimited ? '#28a745' : ((quota?.balance ?? 0) < 10 ? '#dc3545' : 'var(--home-primary)') }}>
                    {quota?.unlimited ? 'Unlimited' : quota?.balance ?? 0}
                  </strong>
                </div>
              )}
            </div>

            {/* Share link */}
            {shareableUrl && (
              <div className="sidebar-share">
                <span className="sidebar-share-label">Share link:</span>
                <code className="sidebar-share-url">{shareableUrl}</code>
                <button
                  type="button"
                  className="sidebar-share-copy"
                  onClick={() => navigator.clipboard.writeText(shareableUrl)}
                  title="Copy link"
                >
                  Copy
                </button>
              </div>
            )}
          </aside>
        </div>
      )}
    </>
  );
}

export default App;
