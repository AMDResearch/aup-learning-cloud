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
import { Modal, Button, Badge, Alert, Form, InputGroup } from 'react-bootstrap';
import type { User, Group } from '@auplc/shared';
import * as api from '@auplc/shared';
import { isGitHubUser as isGitHubUsername } from '@auplc/shared';

interface Props {
  show: boolean;
  user: User | null;
  onHide: () => void;
  onUpdate: () => void;
}

export function EditUserModal({ show, user, onHide, onUpdate }: Props) {
  const [newUsername, setNewUsername] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [selectedGroups, setSelectedGroups] = useState<string[]>([]);
  const [availableGroups, setAvailableGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);

  // Load available groups when modal opens
  useEffect(() => {
    if (show) {
      api.getGroups()
        .then(groups => setAvailableGroups(groups))
        .catch(err => console.error('Failed to load groups:', err));
    }
  }, [show]);

  if (!user) return null;

  const handleStartEdit = () => {
    setNewUsername(user.name);
    setIsAdmin(user.admin);
    setSelectedGroups(user.groups || []);
    setEditMode(true);
    setError(null);
  };

  const handleCancelEdit = () => {
    setEditMode(false);
    setNewUsername('');
    setError(null);
  };

  const handleSaveChanges = async () => {
    const usernameChanged = newUsername !== user.name;
    const adminChanged = isAdmin !== user.admin;
    const groupsChanged = JSON.stringify(selectedGroups.sort()) !== JSON.stringify((user.groups || []).sort());

    if (!usernameChanged && !adminChanged && !groupsChanged) {
      handleCancelEdit();
      return;
    }

    if (usernameChanged && !/^[a-zA-Z0-9_-]+$/.test(newUsername)) {
      setError('Username can only contain letters, numbers, hyphens, and underscores');
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const updates: { name?: string; admin?: boolean; groups?: string[] } = {};
      if (usernameChanged) updates.name = newUsername;
      if (adminChanged) updates.admin = isAdmin;
      if (groupsChanged) updates.groups = selectedGroups;

      await api.updateUser(user.name, updates);
      setEditMode(false);
      onUpdate();
      onHide();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update user');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleString();
  };

  const isGitHubUser = isGitHubUsername(user.name);

  return (
    <Modal show={show} onHide={onHide} size="lg">
      <Modal.Header closeButton>
        <Modal.Title>
          {editMode ? 'Edit User' : 'User Details'}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {error && <Alert variant="danger">{error}</Alert>}

        {editMode ? (
          <div>
            <Alert variant="warning">
              <strong>⚠️ Warning:</strong> Renaming a user is a sensitive operation.
              The user will need to log in with the new username.
            </Alert>

            <Form.Group className="mb-3">
              <Form.Label>Username</Form.Label>
              <InputGroup>
                <Form.Control
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  placeholder="New username"
                  disabled={loading}
                />
              </InputGroup>
              <Form.Text className="text-muted">
                Only letters, numbers, hyphens, and underscores allowed
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Check
                type="switch"
                id="admin-switch"
                label="Grant admin privileges"
                checked={isAdmin}
                onChange={(e) => setIsAdmin(e.target.checked)}
                disabled={loading}
              />
              <Form.Text className="text-muted">
                Admins can manage users and access the admin panel
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Groups</Form.Label>
              <div className="border rounded p-3" style={{ minHeight: '100px', maxHeight: '200px', overflowY: 'auto' }}>
                {availableGroups.length === 0 ? (
                  <div className="text-muted">No groups available</div>
                ) : (
                  availableGroups.map(group => (
                    <Form.Check
                      key={group.name}
                      type="checkbox"
                      id={`group-${group.name}`}
                      label={group.name}
                      checked={selectedGroups.includes(group.name)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedGroups([...selectedGroups, group.name]);
                        } else {
                          setSelectedGroups(selectedGroups.filter(g => g !== group.name));
                        }
                      }}
                      disabled={loading}
                      className="mb-2"
                    />
                  ))
                )}
              </div>
              <Form.Text className="text-muted">
                Select which groups this user belongs to
              </Form.Text>
            </Form.Group>
          </div>
        ) : (
          <>
            <div className="mb-4">
              <h6 className="text-muted mb-3">Basic Information</h6>

              <table className="table table-sm">
                <tbody>
                  <tr>
                    <th style={{ width: '30%' }}>Username</th>
                    <td>
                      {user.name}
                      {isGitHubUser && <Badge bg="info" className="ms-2">GitHub</Badge>}
                    </td>
                  </tr>
                  <tr>
                    <th>Admin Status</th>
                    <td>
                      {user.admin ? (
                        <Badge bg="success">Admin</Badge>
                      ) : (
                        <Badge bg="secondary">Regular User</Badge>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <th>Created</th>
                    <td>{formatDate(user.created)}</td>
                  </tr>
                  <tr>
                    <th>Last Activity</th>
                    <td>{formatDate(user.last_activity)}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="mb-4">
              <h6 className="text-muted mb-3">Server Status</h6>

              <table className="table table-sm">
                <tbody>
                  <tr>
                    <th style={{ width: '30%' }}>Server State</th>
                    <td>
                      {user.pending ? (
                        <Badge bg="warning">{user.pending}</Badge>
                      ) : user.server ? (
                        <Badge bg="success">Running</Badge>
                      ) : (
                        <Badge bg="secondary">Stopped</Badge>
                      )}
                    </td>
                  </tr>
                  {user.server && (
                    <>
                      <tr>
                        <th>Server URL</th>
                        <td>
                          <code>{user.server}</code>
                        </td>
                      </tr>
                      {user.servers && Object.keys(user.servers).length > 0 && (
                        <tr>
                          <th>Named Servers</th>
                          <td>
                            {Object.keys(user.servers).map(name => (
                              <Badge key={name} bg="info" className="me-1">{name}</Badge>
                            ))}
                          </td>
                        </tr>
                      )}
                    </>
                  )}
                </tbody>
              </table>
            </div>

            {user.groups && user.groups.length > 0 && (
              <div className="mb-4">
                <h6 className="text-muted mb-3">Groups</h6>
                <div>
                  {user.groups.map(group => (
                    <Badge key={group} bg="primary" className="me-1">{group}</Badge>
                  ))}
                </div>
              </div>
            )}

            <Alert variant="info" className="mt-4">
              <small>
                <strong>Note:</strong> To reset password, use the "Reset PW" button in the user list.
              </small>
            </Alert>
          </>
        )}
      </Modal.Body>
      <Modal.Footer>
        {editMode ? (
          <>
            <Button variant="secondary" onClick={handleCancelEdit} disabled={loading}>
              Cancel
            </Button>
            <Button variant="dark" onClick={handleSaveChanges} disabled={loading}>
              {loading ? 'Saving...' : 'Save Changes'}
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onHide}>
              Close
            </Button>
            <Button variant="dark" onClick={handleStartEdit}>
              <i className="bi bi-pencil me-1"></i> Edit User
            </Button>
          </>
        )}
      </Modal.Footer>
    </Modal>
  );
}
