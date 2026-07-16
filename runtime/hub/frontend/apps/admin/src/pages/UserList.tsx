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

import React, { useState, useEffect, useCallback, useMemo, memo } from 'react';
import { Table, Button, Form, InputGroup, Badge, Spinner, Alert, ButtonGroup, Modal, Dropdown } from 'react-bootstrap';
import type { User, UserQuota, Server, Group } from '@auplc/shared';
import * as api from '@auplc/shared';
import { isGitHubUser, isNativeUser as isNativeUsername } from '@auplc/shared';
import { CreateUserModal } from '../components/CreateUserModal';
import { SetPasswordModal } from '../components/SetPasswordModal';
import { BatchPasswordModal } from '../components/BatchPasswordModal';
import { EditUserModal } from '../components/EditUserModal';
import { ConfirmModal } from '../components/ConfirmModal';
import { UserDetailModal } from '../components/UserDetailModal';
import { QuotaRefreshModal } from '../components/QuotaRefreshModal';

// Map frontend sort columns to API sort parameters
// JupyterHub API only supports: id, name, last_activity
const sortColumnToApiSort: Record<string, string> = {
  name: 'name',
  lastActivity: 'last_activity',
};

// Utility functions moved outside component to avoid recreation on each render
function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
}

function getServerStatusBadge(user: User): React.ReactNode {
  if (user.pending) {
    return <Badge bg="warning">{user.pending}</Badge>;
  }
  if (user.server) {
    return <Badge bg="success">Running</Badge>;
  }
  return <Badge bg="secondary">Stopped</Badge>;
}

function isNativeUser(user: User): boolean {
  return isNativeUsername(user.name);
}

// Memoized SortIcon component
const SortIcon = memo(function SortIcon({ column, sortColumn, sortDirection }: {
  column: string;
  sortColumn: string;
  sortDirection: 'asc' | 'desc';
}) {
  if (!sortColumnToApiSort[column]) return null;
  if (sortColumn !== column) return <span style={{ opacity: 0.3 }}> ↕</span>;
  return <span> {sortDirection === 'asc' ? '↑' : '↓'}</span>;
});

// Memoized UserRow component to prevent unnecessary re-renders
interface UserRowProps {
  user: User;
  currentUser: string;
  quotaEnabled: boolean;
  quotaMap: Map<string, UserQuota>;
  selectedUsers: Set<string>;
  expandedUsers: Set<string>;
  editingQuota: string | null;
  quotaInput: string;
  actionLoading: string | null;
  baseUrl: string;
  onToggleSelection: (username: string) => void;
  onToggleExpand: (username: string) => void;
  onQuotaEdit: (username: string, balance: number, isUnlimited: boolean) => void;
  onQuotaInputChange: (value: string) => void;
  onQuotaSave: (username: string) => void;
  onQuotaCancel: () => void;
  onStartServer: (user: User) => void;
  onStopServer: (user: User) => void;
  onEditUser: (user: User) => void;
  onPasswordReset: (user: User) => void;
  onDeleteUser: (user: User) => void;
  onViewUsage: (username: string) => void;
}

const UserRow = memo(function UserRow({
  user,
  currentUser,
  quotaEnabled,
  quotaMap,
  selectedUsers,
  expandedUsers,
  editingQuota,
  quotaInput,
  actionLoading,
  baseUrl,
  onToggleSelection,
  onToggleExpand,
  onQuotaEdit,
  onQuotaInputChange,
  onQuotaSave,
  onQuotaCancel,
  onStartServer,
  onStopServer,
  onEditUser,
  onPasswordReset,
  onDeleteUser,
  onViewUsage,
}: UserRowProps) {
  const isExpanded = expandedUsers.has(user.name);
  const isSelected = selectedUsers.has(user.name);
  const quota = quotaMap.get(user.name);
  const isEditingThisQuota = editingQuota === user.name;
  // Protect admin users and the currently logged-in user from deletion
  const isProtected = user.admin || user.name === currentUser;

  return (
    <React.Fragment>
      <tr>
        <td>
          <Button
            variant="link"
            size="sm"
            className="p-0"
            onClick={() => onToggleExpand(user.name)}
            style={{ textDecoration: 'none' }}
          >
            {isExpanded ? '▼' : '▶'}
          </Button>
        </td>
        <td>
          <Form.Check
            type="checkbox"
            checked={isSelected}
            onChange={() => onToggleSelection(user.name)}
          />
        </td>
        <td>
          {user.name}
          {isGitHubUser(user.name) && (
            <Badge bg="info" className="ms-2">GitHub</Badge>
          )}
        </td>
        <td>
          {user.admin ? (
            <Badge bg="success">Admin</Badge>
          ) : (
            <Badge bg="secondary">User</Badge>
          )}
        </td>
        {quotaEnabled && (
          <td>
            {isEditingThisQuota ? (
              <InputGroup size="sm" style={{ width: '100px' }}>
                <Form.Control
                  type="text"
                  value={quotaInput}
                  placeholder="∞ for unlimited"
                  onChange={(e) => onQuotaInputChange(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') onQuotaSave(user.name);
                    if (e.key === 'Escape') onQuotaCancel();
                  }}
                  autoFocus
                />
                <Button
                  variant="success"
                  size="sm"
                  onClick={() => onQuotaSave(user.name)}
                  disabled={actionLoading === `quota-${user.name}`}
                >
                  {actionLoading === `quota-${user.name}` ? <Spinner animation="border" size="sm" /> : '✓'}
                </Button>
              </InputGroup>
            ) : (
              <span
                style={{ cursor: 'pointer', fontWeight: 500 }}
                className={
                  quota?.unlimited
                    ? 'text-success'
                    : (quota?.balance ?? 0) < 10
                      ? 'text-danger'
                      : ''
                }
                onClick={() => onQuotaEdit(user.name, quota?.balance ?? 0, quota?.unlimited === true)}
                title="Click to edit (-1 or ∞ for unlimited)"
              >
                {quota?.unlimited ? '∞' : (quota?.balance ?? 0)}
              </span>
            )}
          </td>
        )}
        <td>{getServerStatusBadge(user)}</td>
        <td>{formatDate(user.last_activity)}</td>
        <td>
          <div className="d-flex align-items-center gap-1">
            {user.server ? (
              <Button
                variant="dark"
                size="sm"
                onClick={() => onStopServer(user)}
                disabled={actionLoading === `stop-${user.name}`}
              >
                {actionLoading === `stop-${user.name}` ? (
                  <Spinner animation="border" size="sm" />
                ) : (
                  'Stop Server'
                )}
              </Button>
            ) : (
              <Button
                variant="dark"
                size="sm"
                onClick={() => onStartServer(user)}
                disabled={actionLoading === `start-${user.name}` || !!user.pending}
              >
                {actionLoading === `start-${user.name}` ? (
                  <Spinner animation="border" size="sm" />
                ) : (
                  'Start Server'
                )}
              </Button>
            )}
            <Dropdown>
              <Dropdown.Toggle variant="light" size="sm" id={`actions-${user.name}`} bsPrefix="btn">
                <i className="bi bi-three-dots-vertical" />
              </Dropdown.Toggle>
              <Dropdown.Menu align="end" popperConfig={{ strategy: 'fixed' }} renderOnMount>
                <Dropdown.Item href={`${baseUrl}spawn/${user.name}`}>
                  <i className="bi bi-rocket me-2" />Spawn Page
                </Dropdown.Item>
                <Dropdown.Item onClick={() => onEditUser(user)}>
                  <i className="bi bi-pencil me-2" />Edit User
                </Dropdown.Item>
                <Dropdown.Item onClick={() => onViewUsage(user.name)}>
                  <i className="bi bi-clock-history me-2" />Usage
                </Dropdown.Item>
                {isNativeUser(user) && (
                  <Dropdown.Item onClick={() => onPasswordReset(user)}>
                    <i className="bi bi-key me-2" />Reset Password
                  </Dropdown.Item>
                )}
                {!isProtected && (
                  <>
                    <Dropdown.Divider />
                    <Dropdown.Item
                      className="text-danger"
                      onClick={() => onDeleteUser(user)}
                      disabled={actionLoading === `delete-${user.name}`}
                    >
                      <i className="bi bi-trash me-2" />Delete
                    </Dropdown.Item>
                  </>
                )}
              </Dropdown.Menu>
            </Dropdown>
          </div>
        </td>
      </tr>
      {/* Expanded User Details */}
      {isExpanded && (
        <tr>
          <td colSpan={quotaEnabled ? 8 : 7} className="bg-body-secondary">
            <UserExpandedDetails user={user} />
          </td>
        </tr>
      )}
    </React.Fragment>
  );
});

// Memoized expanded details component
const UserExpandedDetails = memo(function UserExpandedDetails({ user }: { user: User }) {
  return (
    <div className="d-flex gap-4 p-2">
      {/* User Info */}
      <div style={{ flex: 1 }}>
        <h6 className="mb-2">User</h6>
        <table className="table table-sm table-bordered mb-0" style={{ fontSize: '0.85em' }}>
          <tbody>
            <tr><td style={{ width: '140px' }}><strong>admin</strong></td><td>{user.admin ? 'true' : 'false'}</td></tr>
            <tr><td><strong>auth_state</strong></td><td>{user.auth_state && Object.keys(user.auth_state).length > 0 ? <pre style={{ margin: 0, fontSize: '0.8em', backgroundColor: 'var(--bs-tertiary-bg)', padding: '4px', borderRadius: '4px', maxHeight: '100px', overflow: 'auto' }}>{JSON.stringify(user.auth_state, null, 2)}</pre> : ''}</td></tr>
            <tr><td><strong>created</strong></td><td>{user.created || ''}</td></tr>
            <tr><td><strong>groups</strong></td><td>{user.groups?.join(', ') || ''}</td></tr>
            <tr><td><strong>kind</strong></td><td>user</td></tr>
            <tr><td><strong>last_activity</strong></td><td>{user.last_activity || ''}</td></tr>
            <tr><td><strong>name</strong></td><td>{user.name}</td></tr>
            <tr><td><strong>pending</strong></td><td>{user.pending || ''}</td></tr>
            <tr><td><strong>roles</strong></td><td><Badge bg="secondary">user</Badge></td></tr>
            <tr><td><strong>server</strong></td><td>{user.server || ''}</td></tr>
          </tbody>
        </table>
      </div>
      {/* Server Info */}
      <div style={{ flex: 1 }}>
        <h6 className="mb-2">Server</h6>
        {user.servers && Object.keys(user.servers).length > 0 ? (
          <table className="table table-sm table-bordered mb-0" style={{ fontSize: '0.85em' }}>
            <tbody>
              {Object.entries(user.servers).map(([serverName, server]) => (
                <ServerDetails key={serverName} serverName={serverName} server={server as Server} userName={user.name} />
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-muted mb-0" style={{ fontSize: '0.85em' }}>No server running</p>
        )}
      </div>
    </div>
  );
});

// Memoized server details component
const ServerDetails = memo(function ServerDetails({ serverName, server, userName }: {
  serverName: string;
  server: Server;
  userName: string;
}) {
  return (
    <React.Fragment>
      <tr><td style={{ width: '140px' }}><strong>full_name</strong></td><td>{userName}/{serverName || ''}</td></tr>
      <tr><td><strong>full_progress_url</strong></td><td></td></tr>
      <tr><td><strong>full_url</strong></td><td></td></tr>
      <tr><td><strong>last_activity</strong></td><td>{server.last_activity || ''}</td></tr>
      <tr><td><strong>name</strong></td><td>{serverName}</td></tr>
      <tr><td><strong>pending</strong></td><td>{server.pending || ''}</td></tr>
      <tr><td><strong>progress_url</strong></td><td>{server.progress_url || ''}</td></tr>
      <tr><td><strong>ready</strong></td><td>{server.ready ? 'true' : 'false'}</td></tr>
      <tr><td><strong>started</strong></td><td>{server.started || ''}</td></tr>
      <tr><td><strong>state</strong></td><td>{server.state && Object.keys(server.state).length > 0 ? <pre style={{ margin: 0, fontSize: '0.8em', backgroundColor: 'var(--bs-tertiary-bg)', padding: '4px', borderRadius: '4px', maxHeight: '100px', overflow: 'auto' }}>{JSON.stringify(server.state, null, 2)}</pre> : ''}</td></tr>
      <tr><td><strong>stopped</strong></td><td>{!server.ready ? 'true' : 'false'}</td></tr>
      <tr><td><strong>url</strong></td><td>{server.url || ''}</td></tr>
      <tr><td><strong>user_options</strong></td><td>{server.user_options && Object.keys(server.user_options).length > 0 ? <pre style={{ margin: 0, fontSize: '0.8em', backgroundColor: 'var(--bs-tertiary-bg)', padding: '4px', borderRadius: '4px', maxHeight: '100px', overflow: 'auto' }}>{JSON.stringify(server.user_options, null, 2)}</pre> : ''}</td></tr>
    </React.Fragment>
  );
});

export function UserList() {
  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [loading, setLoading] = useState(true);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [selectedUsers, setSelectedUsers] = useState<Set<string>>(new Set());
  const [onlyActiveServers, setOnlyActiveServers] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(50);
  const [quotaMap, setQuotaMap] = useState<Map<string, UserQuota>>(new Map());
  const [quotaEnabled, setQuotaEnabled] = useState(false);
  const [defaultQuota, setDefaultQuota] = useState(0);
  const [editingQuota, setEditingQuota] = useState<string | null>(null);
  const [quotaInput, setQuotaInput] = useState('');
  const [showBatchQuotaModal, setShowBatchQuotaModal] = useState(false);
  const [batchQuotaInput, setBatchQuotaInput] = useState('100');
  const [sortColumn, setSortColumn] = useState<'name' | 'admin' | 'quota' | 'server' | 'lastActivity'>('lastActivity');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [expandedUsers, setExpandedUsers] = useState<Set<string>>(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [userToDelete, setUserToDelete] = useState<User | null>(null);
  const [showBatchDeleteModal, setShowBatchDeleteModal] = useState(false);
  const [showBatchPasswordModal, setShowBatchPasswordModal] = useState(false);
  const [showBatchGroupModal, setShowBatchGroupModal] = useState(false);
  const [batchGroupMode, setBatchGroupMode] = useState<'add' | 'remove'>('add');
  const [batchGroupName, setBatchGroupName] = useState('');
  const [showQuotaRefreshModal, setShowQuotaRefreshModal] = useState(false);
  const [usageUsername, setUsageUsername] = useState<string | null>(null);

  const jhdata = window.jhdata ?? {};
  const baseUrl = jhdata.base_url ?? '/hub/';
  const currentUser = jhdata.user ?? '';

  // Compute deletable users from selection (exclude admin and current user)
  const deletableSelected = useMemo(() => {
    return Array.from(selectedUsers).filter(username => {
      const user = users.find(u => u.name === username);
      return user && !user.admin && username !== currentUser;
    });
  }, [selectedUsers, users, currentUser]);

  // Compute native (non-GitHub) users from selection for password reset
  const nativeSelected = useMemo(() => {
    return Array.from(selectedUsers).filter(username => {
      const user = users.find(u => u.name === username);
      return user && isNativeUsername(user.name);
    });
  }, [selectedUsers, users]);

  const mutableGroups = useMemo(
    () => groups.filter(group => group.source !== 'system'),
    [groups]
  );

  const selectedUsernames = useMemo(
    () => Array.from(selectedUsers),
    [selectedUsers]
  );

  const allCurrentPageSelected = useMemo(
    () => users.length > 0 && users.every(user => selectedUsers.has(user.name)),
    [selectedUsers, users]
  );

  const selectedOnCurrentPage = useMemo(
    () => users.filter(user => selectedUsers.has(user.name)).length,
    [selectedUsers, users]
  );

  const selectedBatchGroup = useMemo(
    () => groups.find(group => group.name === batchGroupName),
    [batchGroupName, groups]
  );

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setCurrentPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Build API sort parameter
  const apiSort = useMemo(() => {
    const apiColumn = sortColumnToApiSort[sortColumn] || 'last_activity';
    return sortDirection === 'desc' ? `-${apiColumn}` : apiColumn;
  }, [sortColumn, sortDirection]);

  // Build state filter for active servers
  const stateFilter = useMemo(() => {
    return onlyActiveServers ? 'active' : '';
  }, [onlyActiveServers]);

  const loadUsers = useCallback(async (silent = false) => {
    try {
      if (!silent) {
        setLoading(true);
      }
      setError(null);
      const offset = (currentPage - 1) * itemsPerPage;
      const response = await api.getUsers({
        offset,
        limit: itemsPerPage,
        nameFilter: debouncedSearch,
        sort: apiSort,
        state: stateFilter,
      });
      setUsers(response.items || []);
      setTotalUsers(response._pagination?.total || response.items?.length || 0);
      setInitialLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users');
      setInitialLoading(false);
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, [currentPage, itemsPerPage, debouncedSearch, apiSort, stateFilter]);

  const loadQuota = useCallback(async () => {
    try {
      const [quotaData, rates] = await Promise.all([
        api.getAllQuota(),
        api.getQuotaRates(),
      ]);
      const map = new Map<string, UserQuota>();
      for (const q of quotaData.users) {
        map.set(q.username, q);
      }
      setQuotaMap(map);
      setQuotaEnabled(rates.enabled);
      setDefaultQuota(rates.default_quota ?? 0);
    } catch {
      // Quota system might be disabled
      setQuotaEnabled(false);
    }
  }, []);

  const loadGroups = useCallback(async () => {
    try {
      const response = await api.getGroups();
      setGroups(response.groups);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load groups');
    }
  }, []);

  // Load users when pagination, search, sort, or filter changes
  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  // Load quota once on mount
  useEffect(() => {
    loadQuota();
  }, [loadQuota]);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  const handleQuotaEdit = (username: string, currentBalance: number, isUnlimited: boolean) => {
    setEditingQuota(username);
    setQuotaInput(isUnlimited ? '∞' : currentBalance.toString());
  };

  const handleQuotaSave = async (username: string) => {
    try {
      setActionLoading(`quota-${username}`);
      const input = quotaInput.trim();

      // Check if user wants unlimited quota (input is -1 or ∞)
      if (input === '-1' || input === '∞' || input.toLowerCase() === 'unlimited') {
        await api.setUserUnlimited(username, true);
      } else {
        // First revoke unlimited if it was set, then set the amount
        const currentQuota = quotaMap.get(username);
        if (currentQuota?.unlimited) {
          await api.setUserUnlimited(username, false);
        }
        await api.setUserQuota(username, parseInt(input) || 0, 'set');
      }
      await loadQuota();
      setEditingQuota(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update quota');
    } finally {
      setActionLoading(null);
    }
  };

  const handleQuotaCancel = () => {
    setEditingQuota(null);
    setQuotaInput('');
  };

  const handleBatchQuotaSave = async () => {
    if (selectedUsers.size === 0) {
      setError('Please select users first');
      return;
    }

    try {
      setActionLoading('batch-quota');
      const input = batchQuotaInput.trim();
      const isUnlimited = input === '-1' || input === '∞' || input.toLowerCase() === 'unlimited';

      const amount = isUnlimited ? 0 : (parseInt(input) || 0);
      const batchUsers = Array.from(selectedUsers).map(username => {
        const currentQuota = quotaMap.get(username);
        return {
          username,
          amount,
          unlimited: isUnlimited ? true : (currentQuota?.unlimited ? false : undefined),
        };
      });

      // Filter out undefined unlimited values for clean request
      const cleanUsers = batchUsers.map(u => {
        const entry: { username: string; amount: number; unlimited?: boolean } = {
          username: u.username,
          amount: u.amount,
        };
        if (u.unlimited !== undefined) {
          entry.unlimited = u.unlimited;
        }
        return entry;
      });

      await api.batchSetQuota(cleanUsers);

      await loadQuota();
      setShowBatchQuotaModal(false);
      setSelectedUsers(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to batch update quota');
    } finally {
      setActionLoading(null);
    }
  };

  const openBatchGroupModal = (mode: 'add' | 'remove') => {
    if (selectedUsers.size === 0) {
      setError('Please select users first');
      return;
    }
    setBatchGroupMode(mode);
    setBatchGroupName('');
    setError(null);
    setShowBatchGroupModal(true);
  };

  const handleBatchGroupSave = async () => {
    if (selectedUsernames.length === 0) {
      setError('Please select users first');
      return;
    }
    if (!batchGroupName) {
      setError('Please select a group');
      return;
    }

    try {
      setActionLoading('batch-group');
      if (batchGroupMode === 'add') {
        await api.addUsersToGroup(batchGroupName, selectedUsernames);
      } else {
        await api.removeUsersFromGroup(batchGroupName, selectedUsernames);
      }
      await Promise.all([loadUsers(true), loadGroups()]);
      setShowBatchGroupModal(false);
      setSelectedUsers(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update group membership');
    } finally {
      setActionLoading(null);
    }
  };

  // Handle sort column click - only allow sortable columns
  const handleSort = (column: typeof sortColumn) => {
    // Only allow sorting by columns the API supports
    if (!sortColumnToApiSort[column]) return;

    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('desc');
    }
    setCurrentPage(1);
  };

  // Pagination is now handled by the API
  const totalPages = Math.ceil(totalUsers / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;

  // Memoized callbacks to prevent unnecessary re-renders
  const handleToggleSelection = useCallback((username: string) => {
    setSelectedUsers(prev => {
      const newSelected = new Set(prev);
      if (newSelected.has(username)) {
        newSelected.delete(username);
      } else {
        newSelected.add(username);
      }
      return newSelected;
    });
  }, []);

  const handleToggleExpand = useCallback((username: string) => {
    setExpandedUsers(prev => {
      const newExpanded = new Set(prev);
      if (newExpanded.has(username)) {
        newExpanded.delete(username);
      } else {
        newExpanded.add(username);
      }
      return newExpanded;
    });
  }, []);

  const handleQuotaInputChange = useCallback((value: string) => {
    setQuotaInput(value);
  }, []);

  const handleStartServer = useCallback(async (user: User) => {
    try {
      setActionLoading(`start-${user.name}`);
      await api.startServer(user.name);
      await loadUsers(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start server');
    } finally {
      setActionLoading(null);
    }
  }, [loadUsers]);

  const handleStopServer = useCallback(async (user: User) => {
    try {
      setActionLoading(`stop-${user.name}`);
      await api.stopServer(user.name);
      await loadUsers(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop server');
    } finally {
      setActionLoading(null);
    }
  }, [loadUsers]);

  const handleStartAll = async () => {
    const usersToStart = selectedUsers.size > 0
      ? users.filter(u => selectedUsers.has(u.name) && !u.server)
      : users.filter(u => !u.server);

    setActionLoading('start-all');
    for (const user of usersToStart) {
      try {
        await api.startServer(user.name);
      } catch (err) {
        console.error(`Failed to start server for ${user.name}:`, err);
      }
    }
    setActionLoading(null);
    await loadUsers(true);
  };

  const handleStopAll = async () => {
    const usersToStop = selectedUsers.size > 0
      ? users.filter(u => selectedUsers.has(u.name) && u.server)
      : users.filter(u => u.server);

    setActionLoading('stop-all');
    for (const user of usersToStop) {
      try {
        await api.stopServer(user.name);
      } catch (err) {
        console.error(`Failed to stop server for ${user.name}:`, err);
      }
    }
    setActionLoading(null);
    await loadUsers(true);
  };

  const handleShutdownHub = () => {
    if (window.confirm('Are you sure you want to shutdown the hub? This will stop all services.')) {
      window.location.href = `${baseUrl}shutdown`;
    }
  };

  const toggleSelectAll = useCallback(() => {
    setSelectedUsers(prev => {
      const newSelected = new Set(prev);
      if (allCurrentPageSelected) {
        users.forEach(user => newSelected.delete(user.name));
      } else {
        users.forEach(user => newSelected.add(user.name));
      }
      return newSelected;
    });
  }, [allCurrentPageSelected, users]);

  const openPasswordModal = useCallback((user: User) => {
    setSelectedUser(user);
    setShowPasswordModal(true);
  }, []);

  const openEditModal = useCallback((user: User) => {
    setSelectedUser(user);
    setShowEditModal(true);
  }, []);

  const openDeleteModal = useCallback((user: User) => {
    setUserToDelete(user);
    setShowDeleteModal(true);
  }, []);

  const handleDeleteUser = async () => {
    if (!userToDelete) return;
    if (userToDelete.admin || userToDelete.name === currentUser) {
      setError('Cannot delete admin users or yourself');
      setShowDeleteModal(false);
      setUserToDelete(null);
      return;
    }
    try {
      setActionLoading(`delete-${userToDelete.name}`);
      await api.deleteUser(userToDelete.name);
      setShowDeleteModal(false);
      setUserToDelete(null);
      await loadUsers(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete user');
    } finally {
      setActionLoading(null);
    }
  };

  const handleBatchDelete = async () => {
    if (deletableSelected.length === 0) return;
    try {
      setActionLoading('batch-delete');
      await Promise.all(
        deletableSelected.map(username => api.deleteUser(username))
      );
      setShowBatchDeleteModal(false);
      setSelectedUsers(new Set());
      await loadUsers(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to batch delete users');
    } finally {
      setActionLoading(null);
    }
  };

  // Only show full-screen spinner on initial load
  if (initialLoading) {
    return (
      <div className="text-center py-5">
        <Spinner animation="border" role="status">
          <span className="visually-hidden">Loading...</span>
        </Spinner>
      </div>
    );
  }

  return (
    <div>
      {/* Top Controls */}
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div className="d-flex gap-2">
          <Button variant="dark" onClick={() => setShowCreateModal(true)}>
            Add Users
          </Button>
          <Button
            variant="dark"
            onClick={handleStartAll}
            disabled={actionLoading === 'start-all'}
          >
            {actionLoading === 'start-all' ? <Spinner animation="border" size="sm" /> : 'Start All'}
          </Button>
          <Button
            variant="secondary"
            onClick={handleStopAll}
            disabled={actionLoading === 'stop-all'}
          >
            {actionLoading === 'stop-all' ? <Spinner animation="border" size="sm" /> : 'Stop All'}
          </Button>
          {quotaEnabled && (
            <>
              <Button
                variant="secondary"
                onClick={() => setShowBatchQuotaModal(true)}
                disabled={selectedUsers.size === 0}
                title={selectedUsers.size === 0 ? 'Select users first' : `Set quota for ${selectedUsers.size} users`}
              >
                Set Quota ({selectedUsers.size})
              </Button>
              <Button
                variant="secondary"
                onClick={() => setShowQuotaRefreshModal(true)}
                title="Refresh quota for all users"
              >
                <i className="bi bi-arrow-clockwise me-1" />Refresh Quota
              </Button>
            </>
          )}
          <Button
            variant="secondary"
            onClick={() => setShowBatchPasswordModal(true)}
            disabled={nativeSelected.length === 0}
            title={nativeSelected.length === 0 ? 'Select native users first' : `Reset passwords for ${nativeSelected.length} users`}
          >
            Reset PW ({nativeSelected.length})
          </Button>
          <Dropdown>
            <Dropdown.Toggle
              variant="secondary"
              disabled={selectedUsers.size === 0 || mutableGroups.length === 0 || actionLoading !== null}
              title={
                selectedUsers.size === 0
                  ? 'Select users first'
                  : mutableGroups.length === 0
                    ? 'No mutable groups available'
                    : `Update group membership for ${selectedUsers.size} selected users`
              }
            >
              Group Actions ({selectedUsers.size})
            </Dropdown.Toggle>
            <Dropdown.Menu>
              <Dropdown.Item onClick={() => openBatchGroupModal('add')}>
                <i className="bi bi-person-plus me-2" />Add to group
              </Dropdown.Item>
              <Dropdown.Item onClick={() => openBatchGroupModal('remove')}>
                <i className="bi bi-person-dash me-2" />Remove from group
              </Dropdown.Item>
            </Dropdown.Menu>
          </Dropdown>
          <Button
            variant="outline-danger"
            onClick={() => setShowBatchDeleteModal(true)}
            disabled={deletableSelected.length === 0}
            title={deletableSelected.length === 0 ? 'Select users first' : `Delete ${deletableSelected.length} users`}
          >
            Delete ({deletableSelected.length})
          </Button>
          <Button
            variant="danger"
            onClick={handleShutdownHub}
          >
            Shutdown Hub
          </Button>
        </div>
        <div className="d-flex gap-2">
          <Button
            variant="outline-secondary"
            onClick={() => {
              const headers = ['Username', 'Admin', 'Server', 'Last Activity'];
              if (quotaEnabled) headers.splice(2, 0, 'Quota');
              const rows = users.map(u => {
                const row = [u.name, u.admin ? 'Yes' : 'No', u.server ? 'Running' : 'Stopped', u.last_activity ?? ''];
                if (quotaEnabled) {
                  const q = quotaMap.get(u.name);
                  row.splice(2, 0, q?.unlimited ? 'Unlimited' : String(q?.balance ?? 0));
                }
                return row;
              });
              const csv = [headers.join(','), ...rows.map(r => r.map(c => `"${c}"`).join(','))].join('\n');
              const blob = new Blob([csv], { type: 'text/csv' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a'); a.href = url; a.download = 'users.csv'; a.click();
              URL.revokeObjectURL(url);
            }}
            disabled={users.length === 0}
            title="Export current page as CSV"
          >
            <i className="bi bi-download me-1" /> Export
          </Button>
          <Button
            variant="outline-secondary"
            as="a"
            href={`${baseUrl}admin`}
          >
            Legacy Admin
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Search and Filter */}
      <div className="d-flex gap-2 mb-3 align-items-center">
        <InputGroup style={{ maxWidth: '400px' }}>
          <InputGroup.Text><i className="bi bi-search"></i></InputGroup.Text>
          <Form.Control
            placeholder="Search users..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <Button variant="outline-secondary" onClick={() => setSearch('')}>
              Clear
            </Button>
          )}
        </InputGroup>
        {loading && <Spinner animation="border" size="sm" className="ms-2" />}

        <Form.Check
          type="checkbox"
          label="only active servers"
          checked={onlyActiveServers}
          onChange={(e) => {
            setOnlyActiveServers(e.target.checked);
            setCurrentPage(1);
          }}
          className="d-flex align-items-center ms-3"
        />
      </div>

      {selectedUsers.size > 0 && (
        <Alert variant="light" className="border py-2 d-flex justify-content-between align-items-center">
          <span>
            <strong>{selectedUsers.size}</strong> user(s) selected
            {selectedOnCurrentPage !== selectedUsers.size && (
              <span className="text-muted"> · {selectedOnCurrentPage} on this page</span>
            )}
            <span className="text-muted"> · header checkbox selects this page only</span>
          </span>
          <Button variant="outline-secondary" size="sm" onClick={() => setSelectedUsers(new Set())}>
            Clear selection
          </Button>
        </Alert>
      )}

      {/* User Table */}
      <Table striped hover responsive>
        <thead>
          <tr>
            <th style={{ width: '30px' }}></th>
            <th style={{ width: '40px' }}>
              <Form.Check
                type="checkbox"
                checked={allCurrentPageSelected}
                onChange={toggleSelectAll}
                title="Select users on this page"
              />
            </th>
            <th style={{ cursor: 'pointer' }} onClick={() => handleSort('name')}>
              User<SortIcon column="name" sortColumn={sortColumn} sortDirection={sortDirection} />
            </th>
            <th style={{ cursor: 'pointer' }} onClick={() => handleSort('admin')}>
              Admin<SortIcon column="admin" sortColumn={sortColumn} sortDirection={sortDirection} />
            </th>
            {quotaEnabled && (
              <th style={{ width: '120px' }}>
                Quota
              </th>
            )}
            <th>
              Server
            </th>
            <th style={{ cursor: 'pointer' }} onClick={() => handleSort('lastActivity')}>
              Last Activity<SortIcon column="lastActivity" sortColumn={sortColumn} sortDirection={sortDirection} />
            </th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <UserRow
              key={user.name}
              user={user}
              currentUser={currentUser}
              quotaEnabled={quotaEnabled}
              quotaMap={quotaMap}
              selectedUsers={selectedUsers}
              expandedUsers={expandedUsers}
              editingQuota={editingQuota}
              quotaInput={quotaInput}
              actionLoading={actionLoading}
              baseUrl={baseUrl}
              onToggleSelection={handleToggleSelection}
              onToggleExpand={handleToggleExpand}
              onQuotaEdit={handleQuotaEdit}
              onQuotaInputChange={handleQuotaInputChange}
              onQuotaSave={handleQuotaSave}
              onQuotaCancel={handleQuotaCancel}
              onStartServer={handleStartServer}
              onStopServer={handleStopServer}
              onEditUser={openEditModal}
              onPasswordReset={openPasswordModal}
              onDeleteUser={openDeleteModal}
              onViewUsage={setUsageUsername}
            />
          ))}
        </tbody>
      </Table>

      {users.length === 0 && !loading && (
        <div className="text-center text-muted py-4">
          {debouncedSearch || onlyActiveServers ? 'No users match your filters.' : 'No users found.'}
        </div>
      )}

      {/* Pagination */}
      {totalUsers > 0 && (
        <div className="d-flex justify-content-between align-items-center mt-3">
          <div>
            Displaying {startIndex + 1}-{Math.min(startIndex + itemsPerPage, totalUsers)} of {totalUsers}
          </div>
          <div className="d-flex align-items-center gap-2">
            <span>Items per page:</span>
            <Form.Select
              value={itemsPerPage}
              onChange={(e) => {
                setItemsPerPage(Number(e.target.value));
                setCurrentPage(1);
              }}
              style={{ width: 'auto' }}
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </Form.Select>
            <ButtonGroup>
              <Button
                variant="outline-secondary"
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                Previous
              </Button>
              <Button
                variant="outline-secondary"
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
              >
                Next
              </Button>
            </ButtonGroup>
          </div>
        </div>
      )}

      <CreateUserModal
        show={showCreateModal}
        onHide={() => setShowCreateModal(false)}
        onSuccess={() => { loadUsers(); loadQuota(); }}
        quotaEnabled={quotaEnabled}
        defaultQuota={defaultQuota}
      />

      <SetPasswordModal
        show={showPasswordModal}
        user={selectedUser}
        onHide={() => {
          setShowPasswordModal(false);
          setSelectedUser(null);
        }}
      />

      <EditUserModal
        show={showEditModal}
        user={selectedUser}
        onHide={() => {
          setShowEditModal(false);
          setSelectedUser(null);
        }}
        onUpdate={loadUsers}
      />

      {/* Batch Quota Modal */}
      <Modal show={showBatchQuotaModal} onHide={() => setShowBatchQuotaModal(false)}>
        <Modal.Header closeButton>
          <Modal.Title>Batch Set Quota</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Set quota for <strong>{selectedUsers.size}</strong> selected user(s):</p>
          <ul style={{ maxHeight: '150px', overflowY: 'auto', fontSize: '0.9em' }}>
            {Array.from(selectedUsers).slice(0, 10).map(u => (
              <li key={u}>{u}</li>
            ))}
            {selectedUsers.size > 10 && <li>...and {selectedUsers.size - 10} more</li>}
          </ul>
          <Form.Group className="mt-3">
            <Form.Label>Quota Value</Form.Label>
            <Form.Control
              type="text"
              value={batchQuotaInput}
              onChange={(e) => setBatchQuotaInput(e.target.value)}
              placeholder="Enter number or ∞ for unlimited"
            />
            <Form.Text className="text-muted">
              Enter a number, or use <code>-1</code> / <code>∞</code> / <code>unlimited</code> for unlimited quota.
            </Form.Text>
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowBatchQuotaModal(false)}>
            Cancel
          </Button>
          <Button
            variant="dark"
            onClick={handleBatchQuotaSave}
            disabled={actionLoading === 'batch-quota'}
          >
            {actionLoading === 'batch-quota' ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Saving...
              </>
            ) : (
              `Set Quota for ${selectedUsers.size} Users`
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Delete User Confirmation Modal */}
      <ConfirmModal
        show={showDeleteModal}
        title="Delete User"
        message={`Are you sure you want to delete user "${userToDelete?.name}"? This action cannot be undone.`}
        confirmText="Delete"
        confirmVariant="danger"
        onConfirm={handleDeleteUser}
        onCancel={() => {
          setShowDeleteModal(false);
          setUserToDelete(null);
        }}
        loading={actionLoading === `delete-${userToDelete?.name}`}
      />

      {/* Batch Password Reset Modal */}
      <BatchPasswordModal
        show={showBatchPasswordModal}
        usernames={nativeSelected}
        onHide={() => setShowBatchPasswordModal(false)}
      />

      {/* Batch Group Membership Modal */}
      <Modal
        show={showBatchGroupModal}
        onHide={() => {
          if (actionLoading !== 'batch-group') setShowBatchGroupModal(false);
        }}
      >
        <Modal.Header closeButton>
          <Modal.Title>
            {batchGroupMode === 'add' ? 'Add Users to Group' : 'Remove Users from Group'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Alert variant={batchGroupMode === 'add' ? 'info' : 'warning'} className="py-2">
            This will {batchGroupMode} <strong>{selectedUsernames.length}</strong> selected user(s){' '}
            {batchGroupMode === 'add' ? 'to' : 'from'} the selected group.
            {batchGroupMode === 'remove' && ' Users who are not members are skipped.'}
          </Alert>

          {batchGroupMode === 'remove' && selectedBatchGroup?.source === 'github-team' && (
            <Alert variant="warning" className="py-2">
              <i className="bi bi-github me-1" />
              This is a GitHub-synced group. Members synced from GitHub may be added back after login or group synchronization.
              Use this mainly to remove manually added members.
            </Alert>
          )}

          <div className="mb-3">
            <strong>Users:</strong>{' '}
            {selectedUsernames.slice(0, 10).map(name => (
              <Badge key={name} bg="secondary" className="me-1">{name}</Badge>
            ))}
            {selectedUsernames.length > 10 && (
              <Badge bg="secondary">+{selectedUsernames.length - 10} more</Badge>
            )}
          </div>

          <Form.Group>
            <Form.Label>Group</Form.Label>
            <Form.Select
              value={batchGroupName}
              onChange={(e) => setBatchGroupName(e.target.value)}
              disabled={actionLoading === 'batch-group'}
            >
              <option value="" disabled>Select a group</option>
              {mutableGroups.map(group => (
                <option key={group.name} value={group.name}>
                  {group.name} ({group.users.length} {group.users.length === 1 ? 'member' : 'members'})
                  {group.source === 'github-team' ? ' · GitHub' : ''}
                </option>
              ))}
            </Form.Select>
            <Form.Text className="text-muted">
              System-managed groups are read-only and are not listed here.
            </Form.Text>
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button
            variant="secondary"
            onClick={() => setShowBatchGroupModal(false)}
            disabled={actionLoading === 'batch-group'}
          >
            Cancel
          </Button>
          <Button
            variant="dark"
            onClick={handleBatchGroupSave}
            disabled={actionLoading === 'batch-group' || !batchGroupName}
          >
            {actionLoading === 'batch-group' ? (
              <>
                <Spinner animation="border" size="sm" className="me-2" />
                Updating...
              </>
            ) : (
              `${batchGroupMode === 'add' ? 'Add' : 'Remove'} ${selectedUsernames.length} Users`
            )}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Batch Delete Confirmation Modal */}
      <ConfirmModal
        show={showBatchDeleteModal}
        title="Delete Selected Users"
        message={`Are you sure you want to delete ${deletableSelected.length} user(s)? This action cannot be undone.\n\nUsers: ${deletableSelected.slice(0, 10).join(', ')}${deletableSelected.length > 10 ? `, ...and ${deletableSelected.length - 10} more` : ''}`}
        confirmText={`Delete ${deletableSelected.length} Users`}
        confirmVariant="danger"
        onConfirm={handleBatchDelete}
        onCancel={() => setShowBatchDeleteModal(false)}
        loading={actionLoading === 'batch-delete'}
      />

      {/* User Usage Detail Modal */}
      <UserDetailModal
        username={usageUsername}
        onClose={() => setUsageUsername(null)}
      />

      {/* Quota Refresh Modal */}
      <QuotaRefreshModal
        show={showQuotaRefreshModal}
        onHide={() => setShowQuotaRefreshModal(false)}
        onSuccess={loadQuota}
      />
    </div>
  );
}
