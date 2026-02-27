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

import { memo, useMemo, useCallback, useState, useRef, useEffect } from 'react';
import type { Resource, Accelerator, GitHubRepo } from '@auplc/shared';
import { isCurrentUserGitHub } from '@auplc/shared';

interface Props {
  resource: Resource;
  selected: boolean;
  onSelect: (resource: Resource) => void;
  accelerators: Accelerator[];
  selectedAccelerator: Accelerator | null;
  onSelectAccelerator: (accelerator: Accelerator) => void;
  repoUrl: string;
  repoUrlError: string;
  repoValidating: boolean;
  repoValid: boolean;
  repoBranch: string;
  onRepoUrlChange: (value: string) => void;
  allowedGitProviders: string[];
  githubAppName: string;
  githubRepos: GitHubRepo[];
  githubAppInstalled: boolean;
  onSelectGitHubRepo: (repo: GitHubRepo) => void;
}

function formatResourceTag(resource: Resource): string {
  const req = resource.requirements;
  const memory = req.memory.replace('Gi', 'GB');
  let tag = `${req.cpu} CPU, ${memory}`;
  if (req['amd.com/gpu']) {
    tag += `, 1 ${resource.metadata?.accelerator ?? 'GPU'}`;
  }
  if (req['amd.com/npu']) {
    tag += `, 1 NPU`;
  }
  return tag;
}

export const CourseCard = memo(function CourseCard({
  resource,
  selected,
  onSelect,
  accelerators,
  selectedAccelerator,
  onSelectAccelerator,
  repoUrl,
  repoUrlError,
  repoValidating,
  repoValid,
  repoBranch,
  onRepoUrlChange,
  allowedGitProviders,
  githubAppName,
  githubRepos,
  githubAppInstalled,
  onSelectGitHubRepo,
}: Props) {
  const handleClick = useCallback(() => {
    onSelect(resource);
  }, [onSelect, resource]);

  // Memoize available accelerators computation
  const acceleratorKeys = resource.metadata?.acceleratorKeys;
  const availableAccelerators = useMemo(() => {
    if (!acceleratorKeys || acceleratorKeys.length === 0) {
      return [];
    }
    return accelerators.filter(acc => acceleratorKeys.includes(acc.key));
  }, [acceleratorKeys, accelerators]);

  // Memoize resource tag to avoid recalculation
  const resourceTag = useMemo(() => formatResourceTag(resource), [resource]);

  const acceleratorType = resource.metadata?.accelerator ?? 'GPU';

  return (
    <div
      className={`resource-container ${selected ? 'selected' : ''}`}
      onClick={handleClick}
    >
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <input
          type="radio"
          id={resource.key}
          checked={selected}
          onChange={handleClick}
          onClick={(e) => e.stopPropagation()}
        />
        <div style={{ flex: 1 }}>
          <strong>{resource.metadata?.description ?? resource.key}</strong>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}>
            <span className="env-desc">
              {resource.metadata?.subDescription ?? ''}
            </span>
            {resource.metadata?.subDescription && (
              <span className="dot">•</span>
            )}
            <span className="resource-tag">
              {resourceTag}
            </span>
            {resource.metadata?.allowGitClone && (
              <span className="git-clone-badge" title="Supports custom Git repository cloning">
                <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                  <path d="M15.698 7.287 8.712.302a1.03 1.03 0 0 0-1.457 0l-1.45 1.45 1.84 1.84a1.223 1.223 0 0 1 1.55 1.56l1.773 1.774a1.224 1.224 0 0 1 1.267 2.025 1.226 1.226 0 0 1-2.002-1.334L8.445 5.644v4.237a1.226 1.226 0 1 1-1.008-.036V5.585a1.226 1.226 0 0 1-.666-1.608L4.94 2.135 .302 6.772a1.03 1.03 0 0 0 0 1.456l6.986 6.986a1.03 1.03 0 0 0 1.456 0l6.953-6.953a1.031 1.031 0 0 0 0-1.974"/>
                </svg>
                Git Repo
              </span>
            )}
          </div>
        </div>
      </div>

      {/* GPU Selection Panel - only show when this resource is selected and has accelerators */}
      {selected && availableAccelerators.length > 0 && (
        <div className="gpu-selection">
          <h6>Choose {acceleratorType} Node:</h6>
          <div className="gpu-options-container">
            {availableAccelerators.map((acc) => (
              <GpuOption
                key={acc.key}
                accelerator={acc}
                resourceKey={resource.key}
                isSelected={selectedAccelerator?.key === acc.key}
                onSelect={onSelectAccelerator}
              />
            ))}
          </div>
        </div>
      )}

      {/* Git Repository - only show when selected and resource allows git clone */}
      {selected && resource.metadata?.allowGitClone && (
        <div className="gpu-selection" onClick={e => e.stopPropagation()}>
          {/* A) GitHub App Repo Picker */}
          {githubRepos.length > 0 && (
            <RepoPicker
              repos={githubRepos}
              onSelectRepo={onSelectGitHubRepo}
              selectedUrl={repoUrl}
            />
          )}

          {/* B) Manual URL Input */}
          <h6>
            {githubRepos.length > 0 ? 'Or enter URL manually' : (
              <>
                Git Repository URL <span className="optional-label">(optional)</span>
              </>
            )}
            <span className="repo-url-hint" aria-label="Git repository hint">
              ?
              <span className="repo-url-tooltip">
                The repository will be cloned at startup and available during this session only.
                {allowedGitProviders.length > 0 && ` Supports: ${allowedGitProviders.join(', ')}.`}
              </span>
            </span>
          </h6>
          <input
            type="text"
            id={`repoUrlInput-${resource.key}`}
            name="repo_url"
            value={repoUrl}
            onChange={e => onRepoUrlChange(e.target.value)}
            placeholder="https://github.com/owner/repo"
            autoComplete="off"
            spellCheck={false}
            className={`repo-url-input ${repoUrlError ? 'input-error' : ''} ${repoValid ? 'input-valid' : ''}`}
          />
          {repoValidating && (
            <small className="repo-url-validating">Checking repository...</small>
          )}
          {repoValid && !repoValidating && (
            <small className="repo-url-success">
              ✓ Repository verified{repoBranch ? ` · Branch: ${repoBranch}` : ''}
            </small>
          )}
          {repoUrlError && !repoValidating && (
            <small className="repo-url-error">{repoUrlError}</small>
          )}

          {/* GitHub App Install/Manage Prompt (only for GitHub OAuth users) */}
          {githubAppName && isCurrentUserGitHub() && (
            <a
              className="github-app-prompt"
              href={`https://github.com/apps/${githubAppName}/installations/new`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
              </svg>
              {githubAppInstalled ? 'Add access to more repositories' : 'Authorize access to your private repositories'}
            </a>
          )}
        </div>
      )}
    </div>
  );
});

// Separate memoized component for GPU options
interface GpuOptionProps {
  accelerator: Accelerator;
  resourceKey: string;
  isSelected: boolean;
  onSelect: (accelerator: Accelerator) => void;
}

const GpuOption = memo(function GpuOption({
  accelerator,
  resourceKey,
  isSelected,
  onSelect,
}: GpuOptionProps) {
  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    onSelect(accelerator);
  }, [onSelect, accelerator]);

  const handleChange = useCallback(() => {
    onSelect(accelerator);
  }, [onSelect, accelerator]);

  return (
    <div
      className={`gpu-option ${isSelected ? 'selected' : ''}`}
      onClick={handleClick}
    >
      <input
        type="radio"
        name={`gpu_selection_${resourceKey}`}
        checked={isSelected}
        onChange={handleChange}
        onClick={(e) => e.stopPropagation()}
      />
      <div className="gpu-option-details">
        <div className="gpu-option-name">{accelerator.displayName}</div>
        <div className="gpu-option-desc">{accelerator.description}</div>
      </div>
    </div>
  );
});

// Repo picker for GitHub App repos
interface RepoPickerProps {
  repos: GitHubRepo[];
  onSelectRepo: (repo: GitHubRepo) => void;
  selectedUrl: string;
}

const RepoPicker = memo(function RepoPicker({ repos, onSelectRepo, selectedUrl }: RepoPickerProps) {
  const [filter, setFilter] = useState('');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedRepo = useMemo(() =>
    repos.find(r => r.html_url === selectedUrl),
    [repos, selectedUrl]
  );

  const filteredRepos = useMemo(() => {
    if (!filter) return repos;
    const lower = filter.toLowerCase();
    return repos.filter(r =>
      r.full_name.toLowerCase().includes(lower) ||
      (r.description && r.description.toLowerCase().includes(lower))
    );
  }, [repos, filter]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleSelect = useCallback((repo: GitHubRepo) => {
    onSelectRepo(repo);
    setOpen(false);
    setFilter('');
  }, [onSelectRepo]);

  return (
    <div className="repo-picker" ref={containerRef}>
      <h6>Your Repositories</h6>
      <div
        className={`repo-picker-trigger ${open ? 'open' : ''}`}
        onClick={() => setOpen(!open)}
      >
        {selectedRepo ? (
          <>
            <span className="repo-picker-trigger-text">{selectedRepo.full_name}</span>
            {selectedRepo.private && <span className="repo-picker-private">🔒</span>}
          </>
        ) : (
          <span className="repo-picker-trigger-placeholder">Select a repository...</span>
        )}
        <span className="repo-picker-chevron">▾</span>
      </div>
      {open && (
        <div className="repo-picker-dropdown">
          <input
            type="text"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter..."
            className="repo-picker-filter"
            onClick={e => e.stopPropagation()}
            autoFocus
          />
          <div className="repo-picker-list">
            {filteredRepos.map(repo => (
              <div
                key={repo.full_name}
                onClick={() => handleSelect(repo)}
                className={`repo-picker-item ${selectedUrl === repo.html_url ? 'selected' : ''}`}
              >
                <span className="repo-picker-name">{repo.full_name}</span>
                {repo.private && (
                  <span className="repo-picker-private" title="Private repository">🔒</span>
                )}
              </div>
            ))}
            {filteredRepos.length === 0 && (
              <div className="repo-picker-empty">No matching repositories</div>
            )}
          </div>
          <a
            href="https://github.com/settings/installations"
            target="_blank"
            rel="noopener noreferrer"
            className="repo-picker-footer"
            onClick={e => e.stopPropagation()}
          >
            Manage repo access →
          </a>
        </div>
      )}
    </div>
  );
});
