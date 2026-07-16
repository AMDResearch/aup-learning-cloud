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
import { Modal, Button, Form, Alert, Spinner, InputGroup } from 'react-bootstrap';
import type { User } from '@auplc/shared';
import * as api from '@auplc/shared';
import { generateStrongPassword, getPasswordError, isStrongPassword, PASSWORD_RULES } from '@auplc/shared';

interface Props {
  show: boolean;
  user: User | null;
  onHide: () => void;
}

export function SetPasswordModal({ show, user, onHide }: Props) {
  const [password, setPassword] = useState('');
  const [forceChange, setForceChange] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (show) {
      setPassword('');
      setForceChange(false);
      setError(null);
      setSuccess(false);
    }
  }, [show]);

  const allRulesPassed = isStrongPassword(password);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;

    const passwordError = getPasswordError(password);
    if (passwordError) {
      setError(passwordError);
      return;
    }

    setError(null);
    setLoading(true);

    try {
      await api.setPassword({
        username: user.name,
        password,
        force_change: forceChange,
      });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set password');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(password);
  };

  return (
    <Modal show={show} onHide={onHide}>
      <Modal.Header closeButton>
        <Modal.Title>Set Password for {user?.name}</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {success ? (
          <div>
            <Alert variant="success">
              Password successfully updated!
            </Alert>
            <div className="mb-3">
              <strong>New Password:</strong>
              <div className="mt-2 d-flex align-items-center gap-2">
                <code className="fs-5 bg-light p-2 rounded flex-grow-1">
                  {password}
                </code>
                <Button
                  variant="outline-secondary"
                  size="sm"
                  onClick={copyToClipboard}
                  title="Copy to clipboard"
                >
                  <i className="bi bi-clipboard"></i>
                </Button>
              </div>
            </div>
            {forceChange && (
              <Alert variant="info">
                User will be prompted to change password on next login.
              </Alert>
            )}
          </div>
        ) : (
          <Form onSubmit={handleSubmit}>
            {error && <Alert variant="danger">{error}</Alert>}

            <Form.Group className="mb-3">
              <Form.Label>New Password</Form.Label>
              <InputGroup>
                <Form.Control
                  type="text"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter new password"
                  required
                  minLength={8}
                />
                <Button
                  variant="outline-secondary"
                  onClick={() => setPassword(generateStrongPassword())}
                >
                  Generate
                </Button>
              </InputGroup>
              {password.length > 0 && (
                <div className="mt-2" style={{ fontSize: '0.8rem' }}>
                  {PASSWORD_RULES.map((rule, i) => (
                    <div key={i} style={{ color: rule.test(password) ? 'var(--home-green, #34c759)' : 'var(--home-text-muted, #999)' }}>
                      {rule.test(password) ? '✓' : '○'} {rule.label}
                    </div>
                  ))}
                </div>
              )}
              {password.length === 0 && (
                <Form.Text className="text-muted">
                  Min 8 chars, uppercase, lowercase, digit, and special character
                </Form.Text>
              )}
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Force password change on next login"
                checked={forceChange}
                onChange={(e) => setForceChange(e.target.checked)}
              />
            </Form.Group>
          </Form>
        )}
      </Modal.Body>
      <Modal.Footer>
        {success ? (
          <Button variant="dark" onClick={onHide}>
            Done
          </Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onHide}>
              Cancel
            </Button>
            <Button
              variant="dark"
              onClick={handleSubmit}
              disabled={loading || !allRulesPassed}
            >
              {loading ? (
                <>
                  <Spinner animation="border" size="sm" className="me-1" />
                  Setting...
                </>
              ) : (
                'Set Password'
              )}
            </Button>
          </>
        )}
      </Modal.Footer>
    </Modal>
  );
}
