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

// Copyright (C) 2025-2026 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

import { useNavigate, useLocation } from 'react-router-dom';
import { ThemeToggle } from './ThemeToggle';

const tabs = [
  { path: '/users', label: 'Users', icon: 'bi-people' },
  { path: '/groups', label: 'Groups', icon: 'bi-collection' },
  { path: '/dashboard', label: 'Dashboard', icon: 'bi-bar-chart-line' },
];

export function NavBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const jhdata = (window as { jhdata?: { base_url?: string } }).jhdata ?? {};
  const baseUrl = jhdata.base_url ?? '/hub/';

  return (
    <div className="admin-header">
      <div className="admin-breadcrumb">
        <a href={`${baseUrl}home`}>Home</a>
        <span>›</span>
        <span>Administration</span>
      </div>
      <h1>Administration <ThemeToggle /></h1>
      <nav className="admin-nav">
        {tabs.map((tab) => (
          <button
            key={tab.path}
            className={`admin-nav-item${location.pathname === tab.path ? ' active' : ''}`}
            onClick={() => navigate(tab.path)}
          >
            <i className={`bi ${tab.icon}`} />
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
