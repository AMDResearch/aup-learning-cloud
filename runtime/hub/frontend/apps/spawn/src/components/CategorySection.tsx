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

import { memo, useCallback } from 'react';
import type { Resource, ResourceGroup, Accelerator, GitHubRepo } from '@auplc/shared';
import { CourseCard } from './CourseCard';

interface Props {
  group: ResourceGroup;
  expanded: boolean;
  onToggle: (groupName: string) => void;
  selectedResource: Resource | null;
  onSelectResource: (resource: Resource) => void;
  onClearResource: () => void;
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

export const CategorySection = memo(function CategorySection({
  group,
  expanded,
  onToggle,
  selectedResource,
  onSelectResource,
  onClearResource,
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
  const handleToggle = useCallback(() => {
    // When collapsing, clear selection if the selected resource is in this group
    if (expanded && selectedResource != null &&
        group.resources.some(r => r.key === selectedResource.key)) {
      onClearResource();
    }
    onToggle(group.name);
  }, [expanded, selectedResource, group.resources, group.name, onClearResource, onToggle]);

  // Use displayName from API, fallback to group name
  const displayName = group.displayName ?? group.name;

  return (
    <div className={`resource-category ${expanded ? '' : 'collapsed'}`}>
      <div
        className="resource-category-header"
        onClick={handleToggle}
      >
        <h5>📂 {displayName}</h5>
        <span className="collapse-icon">▼</span>
      </div>
      <div className="collapsible-content">
        {group.resources.map((resource) => (
          <CourseCard
            key={resource.key}
            resource={resource}
            selected={selectedResource?.key === resource.key}
            onSelect={onSelectResource}
            accelerators={accelerators}
            selectedAccelerator={selectedAccelerator}
            onSelectAccelerator={onSelectAccelerator}
            repoUrl={repoUrl}
            repoUrlError={repoUrlError}
            repoValidating={repoValidating}
            repoValid={repoValid}
            repoBranch={repoBranch}
            onRepoUrlChange={onRepoUrlChange}
            allowedGitProviders={allowedGitProviders}
            githubAppName={githubAppName}
            githubRepos={githubRepos}
            githubAppInstalled={githubAppInstalled}
            onSelectGitHubRepo={onSelectGitHubRepo}
          />
        ))}
      </div>
    </div>
  );
});
