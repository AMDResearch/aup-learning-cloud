// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

import { useEffect, useState } from 'react';

type Theme = 'light' | 'dark';

function getInitialTheme(): Theme {
  const stored =
    (localStorage.getItem('auplc-theme') as Theme | null) ??
    (localStorage.getItem('jupyterhub-bs-theme') as Theme | null);
  if (stored === 'light' || stored === 'dark') return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute('data-bs-theme', theme);
  localStorage.setItem('auplc-theme', theme);
  localStorage.setItem('jupyterhub-bs-theme', theme);
}

// Apply immediately on module load to avoid flash of unstyled content
applyTheme(getInitialTheme());

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggle = () => setTheme(t => t === 'light' ? 'dark' : 'light');

  return (
    <button
      onClick={toggle}
      className="tw:ml-2 tw:rounded-lg tw:p-2 tw:transition-colors tw:border-0 tw:bg-transparent tw:cursor-pointer text-body-secondary"
      title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
    >
      <i className={`bi ${theme === 'light' ? 'bi-moon-stars-fill' : 'bi-sun-fill'} tw:text-lg`} />
    </button>
  );
}
