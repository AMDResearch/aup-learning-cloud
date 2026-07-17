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

import { useState, useCallback, memo } from 'react';
import { Modal, Button, Form, ListGroup, Alert, Badge } from 'react-bootstrap';
import type { Group } from '@auplc/shared';
import * as api from '@auplc/shared';

// System-managed property keys that should not be shown or edited
const RESERVED_KEYS = new Set(['source']);

// Memoized property list item
const PropertyItem = memo(function PropertyItem({
  propKey,
  value,
  loading,
  readOnly,
  onRemove,
}: {
  propKey: string;
  value: unknown;
  loading: boolean;
  readOnly: boolean;
  onRemove: (key: string) => void;
}) {
  return (
    <ListGroup.Item className="d-flex justify-content-between align-items-center">
      <div>
        <Badge bg="secondary" className="me-2">{propKey}</Badge>
        <span>{String(value)}</span>
      </div>
      {!readOnly && (
        <Button
          variant="outline-danger"
          size="sm"
          onClick={() => onRemove(propKey)}
          disabled={loading}
        >
          Remove
        </Button>
      )}
    </ListGroup.Item>
  );
});

interface Props {
  show: boolean;
  group: Group | null;
  onHide: () => void;
  onUpdate: () => void;
  onDelete: () => void;
}

export function EditGroupModal({ show, group, onHide, onUpdate, onDelete }: Props) {
  const [newPropertyKey, setNewPropertyKey] = useState('');
  const [newPropertyValue, setNewPropertyValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [properties, setProperties] = useState<Record<string, unknown>>({});

  const isGitHubTeam = group?.source === 'github-team';
  const isSystemGroup = group?.source === 'system';
  const isProtected = isGitHubTeam || isSystemGroup;

  // Initialize state when modal opens (exclude reserved keys)
  const handleEnter = () => {
    if (group) {
      const userProps = Object.fromEntries(
        Object.entries(group.properties).filter(([k]) => !RESERVED_KEYS.has(k))
      );
      setProperties(userProps);
      setError(null);
    }
  };

  const handleAddProperty = useCallback(() => {
    if (!newPropertyKey.trim()) {
      setError('Property key cannot be empty');
      return;
    }

    if (RESERVED_KEYS.has(newPropertyKey)) {
      setError(`"${newPropertyKey}" is a reserved key`);
      return;
    }

    setProperties(prev => {
      if (newPropertyKey in prev) {
        setError('Property key already exists');
        return prev;
      }
      setError(null);
      return { ...prev, [newPropertyKey]: newPropertyValue };
    });
    setNewPropertyKey('');
    setNewPropertyValue('');
  }, [newPropertyKey, newPropertyValue]);

  const handleRemoveProperty = useCallback((key: string) => {
    setProperties(prev => {
      const newProps = { ...prev };
      delete newProps[key];
      return newProps;
    });
  }, []);

  const handleApply = async () => {
    if (!group) return;

    try {
      setLoading(true);
      setError(null);
      await api.updateGroup(group.name, { properties });
      onUpdate();
      onHide();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update group');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteGroup = async () => {
    if (!group) return;

    if (!window.confirm(`Are you sure you want to delete group "${group.name}"? This cannot be undone.`)) {
      return;
    }

    try {
      setLoading(true);
      setError(null);
      await api.deleteGroup(group.name);
      onDelete();
      onHide();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete group');
    } finally {
      setLoading(false);
    }
  };

  const handleReleaseProtection = async () => {
    if (!group) return;

    const sourceLabel = isGitHubTeam ? 'GitHub-synced' : 'system-managed';
    if (!window.confirm(
      `Release protection on "${group.name}"?\n\n` +
      `This will convert it from a ${sourceLabel} group to a manually managed group. ` +
      `Members will become editable and the group can be deleted.\n\n` +
      `Note: If a GitHub team with this name still exists, the group will be re-protected when a team member logs in.`
    )) {
      return;
    }

    try {
      setLoading(true);
      setError(null);
      await api.updateGroup(group.name, { release_protection: true });
      onUpdate();
      onHide();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to release protection');
    } finally {
      setLoading(false);
    }
  };

  if (!group) return null;

  return (
    <Modal show={show} onHide={onHide} onEnter={handleEnter}>
      <Modal.Header closeButton>
        <Modal.Title>
          Group Properties: {group.name}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {error && <Alert variant="danger" dismissible onClose={() => setError(null)}>{error}</Alert>}

        {isGitHubTeam && (
          <Alert variant="info" className="d-flex align-items-center gap-2">
            <i className="bi bi-github"></i>
            <span>
              Members are auto-synced from GitHub Teams. You can add users manually,
              but synced members may be re-added or removed when the user next logs in and starts a server.
            </span>
          </Alert>
        )}

        {isSystemGroup && (
          <Alert variant="info">
            System-managed group &mdash; membership is read-only.
          </Alert>
        )}

        {/* Resources (read-only, from config) */}
        {group.resources && group.resources.length > 0 && (
          <div className="mb-3">
            <Form.Label className="fw-semibold">Mapped Resources</Form.Label>
            <div className="d-flex flex-wrap gap-1">
              {group.resources.map(r => (
                <Badge key={r} bg="info" className="fw-normal">{r}</Badge>
              ))}
            </div>
            <Form.Text className="text-muted">
              Resource mappings are defined in values.yaml and cannot be changed from the UI.
            </Form.Text>
          </div>
        )}

        {/* Manage Properties */}
        <div className="mb-3">
          <Form.Label className="fw-semibold">Properties</Form.Label>
          <p className="text-muted small mb-3">
            Properties are key-value pairs that can be used to configure group behavior.
          </p>

          <div className="mb-3">
              <div className="row g-2">
                <div className="col-5">
                  <Form.Control
                    placeholder="Key"
                    value={newPropertyKey}
                    onChange={(e) => setNewPropertyKey(e.target.value)}
                    disabled={loading}
                  />
                </div>
                <div className="col-5">
                  <Form.Control
                    placeholder="Value"
                    value={newPropertyValue}
                    onChange={(e) => setNewPropertyValue(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleAddProperty()}
                    disabled={loading}
                  />
                </div>
                <div className="col-2">
                  <Button variant="dark" onClick={handleAddProperty} disabled={loading} className="w-100">
                    Add Item
                  </Button>
                </div>
              </div>
            </div>

          <ListGroup>
            {Object.keys(properties).length === 0 ? (
              <ListGroup.Item className="text-muted">No properties</ListGroup.Item>
            ) : (
              Object.entries(properties).map(([key, value]) => (
                <PropertyItem
                  key={key}
                  propKey={key}
                  value={value}
                  loading={loading}
                  readOnly={false}
                  onRemove={handleRemoveProperty}
                />
              ))
            )}
          </ListGroup>
        </div>
      </Modal.Body>
      <Modal.Footer className="d-flex justify-content-between">
        {isProtected ? (
          <Button
            variant="outline-warning"
            onClick={handleReleaseProtection}
            disabled={loading}
            title="Convert to a manually managed group"
          >
            Release Protection
          </Button>
        ) : (
          <Button variant="danger" onClick={handleDeleteGroup} disabled={loading}>
            Delete Group
          </Button>
        )}
        <div>
          <Button variant="dark" onClick={handleApply} disabled={loading} className="me-2">
            {loading ? 'Saving...' : 'Save'}
          </Button>
          <Button variant="secondary" onClick={onHide} disabled={loading}>
            Close
          </Button>
        </div>
      </Modal.Footer>
    </Modal>
  );
}
