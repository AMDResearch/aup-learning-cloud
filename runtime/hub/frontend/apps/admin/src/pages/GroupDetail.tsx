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

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Alert, Badge, Button, ButtonGroup, Form, InputGroup, Spinner, Table } from 'react-bootstrap';
import AsyncSelect from 'react-select/async';
import type { MultiValue, StylesConfig } from 'react-select';
import type { Group } from '@auplc/shared';
import * as api from '@auplc/shared';
import { EditGroupModal } from '../components/EditGroupModal';

interface UserOption {
  value: string;
  label: string;
}

const getSelectStyles = (isDark: boolean): StylesConfig<UserOption, true> => ({
  menuPortal: (base) => ({ ...base, zIndex: 9999 }),
  control: (base, state) => ({
    ...base,
    minHeight: '38px',
    backgroundColor: isDark ? '#212529' : base.backgroundColor,
    borderColor: isDark ? '#495057' : base.borderColor,
    '&:hover': {
      borderColor: isDark ? '#6c757d' : base.borderColor,
    },
    ...(state.isFocused && {
      borderColor: isDark ? '#0d6efd' : '#86b7fe',
      boxShadow: '0 0 0 0.25rem rgba(13, 110, 253, 0.25)',
    }),
  }),
  menu: (base) => ({
    ...base,
    backgroundColor: isDark ? '#212529' : base.backgroundColor,
    border: isDark ? '1px solid #495057' : base.border,
  }),
  option: (base, state) => ({
    ...base,
    backgroundColor: state.isFocused
      ? (isDark ? '#495057' : '#deebff')
      : (isDark ? '#212529' : base.backgroundColor),
    color: isDark ? '#fff' : base.color,
    '&:active': {
      backgroundColor: isDark ? '#6c757d' : '#b2d4ff',
    },
  }),
  input: (base) => ({
    ...base,
    color: isDark ? '#fff' : base.color,
  }),
  placeholder: (base) => ({
    ...base,
    color: isDark ? '#adb5bd' : base.color,
  }),
  multiValue: (base) => ({
    ...base,
    backgroundColor: '#6c757d',
  }),
  multiValueLabel: (base) => ({
    ...base,
    color: 'white',
  }),
  multiValueRemove: (base) => ({
    ...base,
    color: 'white',
    ':hover': {
      backgroundColor: '#5a6268',
      color: 'white',
    },
  }),
  noOptionsMessage: (base) => ({
    ...base,
    color: isDark ? '#adb5bd' : base.color,
  }),
  loadingMessage: (base) => ({
    ...base,
    color: isDark ? '#adb5bd' : base.color,
  }),
});

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function SourceBadge({ group }: { group: Group }) {
  if (group.source === 'github-team') {
    return <Badge bg="dark" title="Synced from GitHub Teams"><i className="bi bi-github me-1" />GitHub</Badge>;
  }
  if (group.source === 'system') {
    return <Badge bg="info" title="System-managed group">System</Badge>;
  }
  return <Badge bg="secondary" title="Manually managed group">Manual</Badge>;
}

function ResourceBadges({ resources }: { resources: string[] }) {
  if (resources.length === 0) return <span className="text-muted">No mapped resources</span>;
  return (
    <div className="d-flex flex-wrap gap-1">
      {resources.map(resource => <Badge key={resource} bg="info" className="fw-normal">{resource}</Badge>)}
    </div>
  );
}

export function GroupDetail() {
  const params = useParams();
  const navigate = useNavigate();
  const groupName = safeDecode(params.groupName ?? '');

  const [group, setGroup] = useState<Group | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [memberSearch, setMemberSearch] = useState('');
  const [selectedMembers, setSelectedMembers] = useState<Set<string>>(new Set());
  const [usersToAdd, setUsersToAdd] = useState<UserOption[]>([]);
  const [showEditModal, setShowEditModal] = useState(false);
  const [isDark, setIsDark] = useState(() =>
    document.documentElement.getAttribute('data-bs-theme') === 'dark'
  );

  const isReadOnly = group?.source === 'system';
  const isGitHubTeam = group?.source === 'github-team';

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.getAttribute('data-bs-theme') === 'dark');
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-bs-theme'],
    });
    return () => observer.disconnect();
  }, []);

  const loadGroup = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setError(null);
      const response = await api.getGroups();
      const nextGroup = response.groups.find(candidate => candidate.name === groupName) ?? null;
      setGroup(nextGroup);
      setSelectedMembers(prev => {
        if (!nextGroup) return new Set();
        const currentMembers = new Set(nextGroup.users);
        return new Set(Array.from(prev).filter(member => currentMembers.has(member)));
      });
      if (!nextGroup) {
        setError(`Group "${groupName}" was not found.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load group');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [groupName]);

  useEffect(() => {
    loadGroup();
  }, [loadGroup]);

  useEffect(() => {
    setMemberSearch('');
    setSelectedMembers(new Set());
    setUsersToAdd([]);
    setNotice(null);
    setError(null);
  }, [groupName]);

  const filteredMembers = useMemo(() => {
    if (!group) return [];
    const searchLower = memberSearch.trim().toLowerCase();
    if (!searchLower) return [...group.users].sort();
    return group.users
      .filter(member => member.toLowerCase().includes(searchLower))
      .sort();
  }, [group, memberSearch]);

  const selectedVisibleCount = useMemo(
    () => filteredMembers.filter(member => selectedMembers.has(member)).length,
    [filteredMembers, selectedMembers]
  );

  const allVisibleSelected = filteredMembers.length > 0 && selectedVisibleCount === filteredMembers.length;

  const loadUserOptions = useCallback(async (inputValue: string): Promise<UserOption[]> => {
    if (!inputValue || inputValue.length < 1 || !group) return [];

    try {
      const response = await api.getUsers({ offset: 0, limit: 20, nameFilter: inputValue });
      const existingMembers = new Set(group.users);
      const pendingAdds = new Set(usersToAdd.map(user => user.value));
      return (response.items || [])
        .filter(user => !existingMembers.has(user.name) && !pendingAdds.has(user.name))
        .map(user => ({
          value: user.name,
          label: user.admin ? `${user.name} (Admin)` : user.name,
        }));
    } catch (err) {
      console.error('Failed to load users:', err);
      return [];
    }
  }, [group, usersToAdd]);

  const toggleMember = (member: string) => {
    setSelectedMembers(prev => {
      const next = new Set(prev);
      if (next.has(member)) {
        next.delete(member);
      } else {
        next.add(member);
      }
      return next;
    });
  };

  const toggleVisibleMembers = () => {
    setSelectedMembers(prev => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        filteredMembers.forEach(member => next.delete(member));
      } else {
        filteredMembers.forEach(member => next.add(member));
      }
      return next;
    });
  };

  const handleAddMembers = async () => {
    if (!group || usersToAdd.length === 0 || isReadOnly) return;

    try {
      setActionLoading('add-members');
      setError(null);
      setNotice(null);
      const usernames = usersToAdd.map(user => user.value);
      const updatedGroup = await api.addUsersToGroup(group.name, usernames);
      setGroup(updatedGroup);
      setUsersToAdd([]);
      setNotice(`Added ${usernames.length} user(s) to ${group.name}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add members');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRemoveSelected = async () => {
    if (!group || selectedMembers.size === 0 || isReadOnly) return;

    const usernames = Array.from(selectedMembers);
    if (!window.confirm(`Remove ${usernames.length} member(s) from "${group.name}"?`)) {
      return;
    }

    try {
      setActionLoading('remove-members');
      setError(null);
      setNotice(null);
      const updatedGroup = await api.removeUsersFromGroup(group.name, usernames);
      setGroup(updatedGroup);
      setSelectedMembers(new Set());
      setNotice(`Removed ${usernames.length} member(s) from ${group.name}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove members');
    } finally {
      setActionLoading(null);
    }
  };

  const handleEditUpdate = async () => {
    await loadGroup(true);
  };

  const handleDelete = () => {
    navigate('/groups');
  };

  if (loading) {
    return (
      <div className="text-center py-5">
        <Spinner animation="border" role="status">
          <span className="visually-hidden">Loading...</span>
        </Spinner>
      </div>
    );
  }

  if (!group) {
    return (
      <div>
        <Button variant="outline-secondary" className="mb-3" onClick={() => navigate('/groups')}>
          <i className="bi bi-arrow-left me-1" />Back to Groups
        </Button>
        {error && <Alert variant="danger">{error}</Alert>}
      </div>
    );
  }

  return (
    <div>
      <div className="d-flex justify-content-between align-items-start mb-3">
        <div>
          <Button variant="link" className="p-0 mb-2" onClick={() => navigate('/groups')}>
            <i className="bi bi-arrow-left me-1" />Back to Groups
          </Button>
          <div className="d-flex align-items-center gap-2">
            <h2 className="mb-0">{group.name}</h2>
            <SourceBadge group={group} />
          </div>
          <div className="text-muted mt-1">
            {group.users.length} {group.users.length === 1 ? 'member' : 'members'}
            {(group.resources?.length ?? 0) > 0 && ` · ${group.resources!.length} resources`}
          </div>
        </div>
        <ButtonGroup>
          <Button variant="outline-secondary" onClick={() => setShowEditModal(true)}>
            Properties
          </Button>
          <Button variant="outline-secondary" onClick={() => loadGroup(true)} disabled={actionLoading !== null}>
            <i className="bi bi-arrow-clockwise me-1" />Refresh
          </Button>
        </ButtonGroup>
      </div>

      {error && <Alert variant="danger" dismissible onClose={() => setError(null)}>{error}</Alert>}
      {notice && <Alert variant="success" dismissible onClose={() => setNotice(null)}>{notice}</Alert>}

      {isReadOnly && (
        <Alert variant="info">
          System-managed group membership is read-only. You can view members and edit group properties, but cannot add or remove members.
        </Alert>
      )}

      {isGitHubTeam && (
        <Alert variant="light" className="border">
          <i className="bi bi-github me-1" />
          This group is synced from GitHub Teams. Manual additions are allowed, but GitHub-synced members may be added back after login or synchronization.
        </Alert>
      )}

      <div className="mb-4">
        <h5>Mapped Resources</h5>
        <ResourceBadges resources={group.resources ?? []} />
      </div>

      {!isReadOnly && (
        <div className="border rounded p-3 mb-4">
          <h5>Add Members</h5>
          <div className="d-flex gap-2 align-items-start">
            <div style={{ flex: 1 }}>
              <AsyncSelect<UserOption, true>
                isMulti
                cacheOptions
                defaultOptions={false}
                value={usersToAdd}
                loadOptions={loadUserOptions}
                onChange={(newValue: MultiValue<UserOption>) => setUsersToAdd([...newValue])}
                isDisabled={actionLoading === 'add-members'}
                isLoading={actionLoading === 'add-members'}
                placeholder="Search users to add..."
                noOptionsMessage={({ inputValue }) => inputValue ? 'No users found' : 'Type to search users'}
                loadingMessage={() => 'Searching...'}
                menuPortalTarget={document.body}
                styles={getSelectStyles(isDark)}
              />
              <Form.Text className="text-muted">
                Existing members are hidden from the search results.
              </Form.Text>
            </div>
            <Button
              variant="dark"
              onClick={handleAddMembers}
              disabled={usersToAdd.length === 0 || actionLoading === 'add-members'}
            >
              {actionLoading === 'add-members' ? (
                <><Spinner animation="border" size="sm" className="me-1" />Adding...</>
              ) : (
                `Add ${usersToAdd.length || ''}`.trim()
              )}
            </Button>
          </div>
        </div>
      )}

      <div className="d-flex justify-content-between align-items-center mb-3">
        <h5 className="mb-0">Members</h5>
        <div className="d-flex gap-2">
          {!isReadOnly && (
            <Button
              variant="outline-danger"
              size="sm"
              onClick={handleRemoveSelected}
              disabled={selectedMembers.size === 0 || actionLoading === 'remove-members'}
            >
              {actionLoading === 'remove-members' ? (
                <><Spinner animation="border" size="sm" className="me-1" />Removing...</>
              ) : (
                `Remove Selected (${selectedMembers.size})`
              )}
            </Button>
          )}
          {selectedMembers.size > 0 && (
            <Button variant="outline-secondary" size="sm" onClick={() => setSelectedMembers(new Set())}>
              Clear selection
            </Button>
          )}
        </div>
      </div>

      <InputGroup className="mb-3" style={{ maxWidth: '420px' }}>
        <InputGroup.Text><i className="bi bi-search" /></InputGroup.Text>
        <Form.Control
          placeholder="Search members..."
          value={memberSearch}
          onChange={(event) => setMemberSearch(event.target.value)}
        />
        {memberSearch && (
          <Button variant="outline-secondary" onClick={() => setMemberSearch('')}>
            Clear
          </Button>
        )}
      </InputGroup>

      <Table striped hover responsive>
        <thead>
          <tr>
            <th style={{ width: '40px' }}>
              <Form.Check
                type="checkbox"
                checked={allVisibleSelected}
                disabled={filteredMembers.length === 0}
                onChange={toggleVisibleMembers}
                title="Select visible members"
              />
            </th>
            <th>Username</th>
          </tr>
        </thead>
        <tbody>
          {filteredMembers.map(member => (
            <tr key={member}>
              <td>
                <Form.Check
                  type="checkbox"
                  checked={selectedMembers.has(member)}
                  onChange={() => toggleMember(member)}
                />
              </td>
              <td>{member}</td>
            </tr>
          ))}
        </tbody>
      </Table>

      {filteredMembers.length === 0 && (
        <div className="text-center text-muted py-4">
          {memberSearch ? 'No members match your search.' : 'This group has no members.'}
        </div>
      )}

      <EditGroupModal
        show={showEditModal}
        group={group}
        onHide={() => setShowEditModal(false)}
        onUpdate={handleEditUpdate}
        onDelete={handleDelete}
      />
    </div>
  );
}
