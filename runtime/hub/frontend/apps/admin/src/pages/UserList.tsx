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
import { useNavigate } from 'react-router-dom';
import { Table, Button, Form, InputGroup, Badge, Spinner, Alert, ButtonGroup, Modal } from 'react-bootstrap';
import type { User, UserQuota, Server } from '@auplc/shared';
import * as api from '@auplc/shared';
import { isGitHubUser, isNativeUser as isNativeUsername } from '@auplc/shared';
import { CreateUserModal } from '../components/CreateUserModal';
import { SetPasswordModal } from '../components/SetPasswordModal';
import { EditUserModal } from '../components/EditUserModal';
import { ConfirmModal } from '../components/ConfirmModal';

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
}

const UserRow = memo(function UserRow({
  user,
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
}: UserRowProps) {
  const isExpanded = expandedUsers.has(user.name);
  const isSelected = selectedUsers.has(user.name);
  const quota = quotaMap.get(user.name);
  const isEditingThisQuota = editingQuota === user.name;

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
          <ButtonGroup size="sm">
            {user.server ? (
              <Button
                variant="dark"
                onClick={() => onStopServer(user)}
                disabled={actionLoading === `stop-${user.name}`}
                title="Stop Server"
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
                onClick={() => onStartServer(user)}
                disabled={actionLoading === `start-${user.name}` || !!user.pending}
                title="Start Server"
              >
                {actionLoading === `start-${user.name}` ? (
                  <Spinner animation="border" size="sm" />
                ) : (
                  'Start Server'
                )}
              </Button>
            )}

            <Button
              variant="light"
              as="a"
              href={`${baseUrl}spawn/${user.name}`}
              title="Spawn Page"
            >
              Spawn Page
            </Button>

            <Button
              variant="light"
              onClick={() => onEditUser(user)}
              title="Edit User"
            >
              Edit User
            </Button>

            {isNativeUser(user) && user.name !== 'admin' && (
              <Button
                variant="light"
                onClick={() => onPasswordReset(user)}
                title="Reset Password"
              >
                <i className="bi bi-key"></i> Reset PW
              </Button>
            )}
            {user.name !== 'admin' && (
              <Button
                variant="outline-danger"
                onClick={() => onDeleteUser(user)}
                title="Delete User"
                disabled={actionLoading === `delete-${user.name}`}
              >
                {actionLoading === `delete-${user.name}` ? (
                  <Spinner animation="border" size="sm" />
                ) : (
                  'Delete'
                )}
              </Button>
            )}
          </ButtonGroup>
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
  const navigate = useNavigate();
  const [users, setUsers] = useState<User[]>([]);
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
  const [editingQuota, setEditingQuota] = useState<string | null>(null);
  const [quotaInput, setQuotaInput] = useState('');
  const [showBatchQuotaModal, setShowBatchQuotaModal] = useState(false);
  const [batchQuotaInput, setBatchQuotaInput] = useState('100');
  const [sortColumn, setSortColumn] = useState<'name' | 'admin' | 'quota' | 'server' | 'lastActivity'>('lastActivity');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [expandedUsers, setExpandedUsers] = useState<Set<string>>(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [userToDelete, setUserToDelete] = useState<User | null>(null);

  const jhdata = window.jhdata ?? {};
  const baseUrl = jhdata.base_url ?? '/hub/';

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
      const quotaData = await api.getAllQuota();
      const map = new Map<string, UserQuota>();
      for (const q of quotaData.users) {
        map.set(q.username, q);
      }
      setQuotaMap(map);
      setQuotaEnabled(true);
    } catch {
      // Quota system might be disabled
      setQuotaEnabled(false);
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

      for (const username of selectedUsers) {
        try {
          if (isUnlimited) {
            await api.setUserUnlimited(username, true);
          } else {
            const currentQuota = quotaMap.get(username);
            if (currentQuota?.unlimited) {
              await api.setUserUnlimited(username, false);
            }
            await api.setUserQuota(username, parseInt(input) || 0, 'set');
          }
        } catch (err) {
          console.error(`Failed to set quota for ${username}:`, err);
        }
      }

      await loadQuota();
      setShowBatchQuotaModal(false);
      setSelectedUsers(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to batch update quota');
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

  const handleStartServer = async (user: User) => {
    try {
      setActionLoading(`start-${user.name}`);
      await api.startServer(user.name);
      await loadUsers(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start server');
    } finally {
      setActionLoading(null);
    }
  };

  const handleStopServer = async (user: User) => {
    try {
      setActionLoading(`stop-${user.name}`);
      await api.stopServer(user.name);
      await loadUsers(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop server');
    } finally {
      setActionLoading(null);
    }
  };

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
      if (prev.size === users.length) {
        return new Set();
      } else {
        return new Set(users.map(u => u.name));
      }
    });
  }, [users]);

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

  // Memoize start/stop server handlers with useCallback
  const handleStartServerCallback = useCallback((user: User) => {
    handleStartServer(user);
  }, []);

  const handleStopServerCallback = useCallback((user: User) => {
    handleStopServer(user);
  }, []);

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
            <Button
              variant="secondary"
              onClick={() => setShowBatchQuotaModal(true)}
              disabled={selectedUsers.size === 0}
              title={selectedUsers.size === 0 ? 'Select users first' : `Set quota for ${selectedUsers.size} users`}
            >
              Set Quota ({selectedUsers.size})
            </Button>
          )}
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
            onClick={() => navigate('/groups')}
          >
            Manage Groups
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

      {/* User Table */}
      <Table striped hover responsive>
        <thead>
          <tr>
            <th style={{ width: '30px' }}></th>
            <th style={{ width: '40px' }}>
              <Form.Check
                type="checkbox"
                checked={selectedUsers.size === users.length && users.length > 0}
                onChange={toggleSelectAll}
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
              onStartServer={handleStartServerCallback}
              onStopServer={handleStopServerCallback}
              onEditUser={openEditModal}
              onPasswordReset={openPasswordModal}
              onDeleteUser={openDeleteModal}
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
        onSuccess={loadUsers}
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
    </div>
  );
}
