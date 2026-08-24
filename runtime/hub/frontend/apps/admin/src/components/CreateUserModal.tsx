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

import { useState, useCallback, useMemo } from 'react';
import { Modal, Button, Form, Alert, Spinner, InputGroup, Row, Col, Badge } from 'react-bootstrap';
import * as api from '@auplc/shared';
import { generateStrongPassword, getPasswordError, isStrongPassword, PASSWORD_RULES } from '@auplc/shared';

interface Props {
  show: boolean;
  onHide: () => void;
  onSuccess: () => void;
  quotaEnabled?: boolean;
  defaultQuota?: number;
}

interface CreatedUser {
  username: string;
  password: string;
  status: 'created' | 'existed' | 'failed';
  passwordSet: boolean;
  quotaSet: boolean;
  error?: string;
}

const parseBoundedInteger = (value: string, fallback: number, min: number, max: number) => {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) return fallback;
  return Math.min(Math.max(parsed, min), max);
};

export function CreateUserModal({ show, onHide, onSuccess, quotaEnabled = false, defaultQuota = 0 }: Props) {
  const [usernames, setUsernames] = useState('');
  const [password, setPassword] = useState('');
  const [generateRandom, setGenerateRandom] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [forceChange, setForceChange] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdUsers, setCreatedUsers] = useState<CreatedUser[]>([]);
  const [step, setStep] = useState<'input' | 'result'>('input');
  const [prefix, setPrefix] = useState('');
  const [count, setCount] = useState(10);
  const [startNum, setStartNum] = useState(1);
  const [suffixWidth, setSuffixWidth] = useState(2);
  const [quotaValue, setQuotaValue] = useState(String(defaultQuota || 0));

  const handleGenerateNames = useCallback(() => {
    if (!prefix.trim()) return;
    const names = Array.from({ length: count }, (_, i) => {
      const suffix = String(startNum + i);
      return `${prefix.trim()}${suffixWidth > 0 ? suffix.padStart(suffixWidth, '0') : suffix}`;
    });
    setUsernames(names.join('\n'));
  }, [prefix, count, startNum, suffixWidth]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    try {
      const names = usernames
        .split('\n')
        .map(n => n.trim())
        .filter(n => n.length > 0);

      if (names.length === 0) {
        setError('Please enter at least one username');
        return;
      }

      const passwordError = generateRandom ? null : getPasswordError(password);
      if (passwordError) {
        setError(passwordError);
        return;
      }

      setLoading(true);

      // Generate passwords for all users upfront
      const passwordMap = new Map(
        names.map(username => [
          username,
          generateRandom ? generateStrongPassword() : password,
        ])
      );

      const warnings: string[] = [];

      let quota: { amount?: number; unlimited?: boolean } | undefined;
      if (quotaEnabled) {
        const input = quotaValue.trim();
        const isUnlimited = input === '-1' || input === '∞' || input.toLowerCase() === 'unlimited';
        if (!isUnlimited && input !== '' && !/^\d+$/.test(input)) {
          setError('Initial quota must be a non-negative integer, -1, or unlimited');
          return;
        }
        const amount = isUnlimited ? 0 : (Number(input) || 0);
        if (isUnlimited || amount > 0) {
          quota = isUnlimited ? { amount: 0, unlimited: true } : { amount };
        }
      }

      const userEntries = names.map(username => ({ username, password: passwordMap.get(username)! }));

      const response = await api.provisionUsers({
        users: userEntries,
        admin: isAdmin,
        force_change: forceChange,
        quota,
      });

      const results = new Map<string, CreatedUser>();
      for (const [index, entry] of userEntries.entries()) {
        const r = response.results[index];
        const displayUsername = r?.username || entry.username;
        results.set(`${index}:${entry.username}`, {
          username: displayUsername,
          password: entry.password,
          status: r?.status === 'existed'
            ? 'existed'
            : r?.created || r?.status === 'success'
              ? 'created'
              : 'failed',
          passwordSet: r?.password_set ?? false,
          quotaSet: r?.quota_set ?? false,
          error: r?.error,
        });
      }

      const existedNames = response.results.filter(r => r.status === 'existed').map(r => r.username);
      if (existedNames.length > 0) {
        warnings.push(`${existedNames.length} user(s) already existed: ${existedNames.join(', ')}`);
      }
      const failedResults = response.results.filter(r => r.status === 'failed');
      if (failedResults.length > 0) {
        warnings.push(...failedResults.map(r => `${r.username}: ${r.error || 'Provisioning failed'}`));
      }

      // Set warnings as non-fatal error for display
      if (warnings.length > 0) {
        setError(warnings.join('\n'));
      }

      setCreatedUsers(Array.from(results.values()));
      setStep('result');
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create users');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setUsernames('');
    setPassword('');
    setGenerateRandom(true);
    setIsAdmin(false);
    setForceChange(true);
    setError(null);
    setCreatedUsers([]);
    setStep('input');
    setPrefix('');
    setCount(10);
    setStartNum(1);
    setSuffixWidth(2);
    setQuotaValue(String(defaultQuota || 0));
    onHide();
  };

  const usersWithPasswords = useMemo(
    () => createdUsers.filter(u => u.passwordSet),
    [createdUsers]
  );

  const copyToClipboard = () => {
    const text = usersWithPasswords
      .map(u => `${u.username}\t${u.password}`)
      .join('\n');
    navigator.clipboard.writeText(text);
  };

  const downloadCsv = () => {
    const header = 'username,password,status\n';
    const rows = createdUsers
      .map(u => `${u.username},${u.passwordSet ? u.password : ''},${u.status}`)
      .join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `users-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const manualPasswordError = generateRandom ? null : getPasswordError(password);
  const canSubmit = !loading && (generateRandom || isStrongPassword(password));

  return (
    <Modal show={show} onHide={handleClose} size="lg">
      <Modal.Header closeButton>
        <Modal.Title>
          {step === 'input' ? 'Create Users' : 'Results'}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {step === 'input' ? (
          <Form onSubmit={handleSubmit}>
            {error && <Alert variant="danger">{error}</Alert>}

            <Form.Group className="mb-3">
              <Form.Label className="text-muted small mb-1">Quick generate</Form.Label>
              <Row className="g-2 align-items-end">
                <Col>
                  <Form.Control
                    size="sm"
                    type="text"
                    value={prefix}
                    onChange={(e) => setPrefix(e.target.value)}
                    placeholder="Prefix, e.g. student"
                  />
                </Col>
                <Col xs="auto">
                  <InputGroup size="sm">
                    <InputGroup.Text>from</InputGroup.Text>
                    <Form.Control
                      type="number"
                      min={0}
                      max={9999}
                      value={startNum}
                      onChange={(e) => setStartNum(parseBoundedInteger(e.target.value, 1, 0, 9999))}
                      style={{ width: 70 }}
                    />
                  </InputGroup>
                </Col>
                <Col xs="auto">
                  <InputGroup size="sm">
                    <InputGroup.Text>digits (0 = none)</InputGroup.Text>
                    <Form.Control
                      type="number"
                      min={0}
                      max={6}
                      value={suffixWidth}
                      onChange={(e) => setSuffixWidth(parseBoundedInteger(e.target.value, 0, 0, 6))}
                      style={{ width: 60 }}
                    />
                  </InputGroup>
                </Col>
                <Col xs="auto">
                  <InputGroup size="sm">
                    <InputGroup.Text>count</InputGroup.Text>
                    <Form.Control
                      type="number"
                      min={1}
                      max={1000}
                      value={count}
                      onChange={(e) => setCount(parseBoundedInteger(e.target.value, 1, 1, 1000))}
                      style={{ width: 70 }}
                    />
                  </InputGroup>
                </Col>
                <Col xs="auto">
                  <Button
                    size="sm"
                    variant="outline-primary"
                    onClick={handleGenerateNames}
                    disabled={!prefix.trim()}
                  >
                    Fill
                  </Button>
                </Col>
              </Row>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Usernames (one per line)</Form.Label>
              <Form.Control
                as="textarea"
                rows={5}
                value={usernames}
                onChange={(e) => setUsernames(e.target.value)}
                placeholder="user1&#10;user2&#10;user3"
                required
              />
            </Form.Group>

            {quotaEnabled && (
              <Form.Group className="mb-3">
                <Form.Label>Initial Quota</Form.Label>
                <Form.Control
                  type="text"
                  value={quotaValue}
                  onChange={(e) => setQuotaValue(e.target.value)}
                  placeholder="e.g. 100, or -1 for unlimited"
                />
                <Form.Text className="text-muted">
                  Leave as 0 to skip. Use -1 or &quot;unlimited&quot; for unlimited.
                </Form.Text>
              </Form.Group>
            )}

            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Generate random passwords"
                checked={generateRandom}
                onChange={(e) => setGenerateRandom(e.target.checked)}
              />
            </Form.Group>

            <Alert variant="info" className="py-2">
              <div className="fw-semibold mb-1">Native passwords must meet all rules before users are created.</div>
              <div className="small">
                {PASSWORD_RULES.map((rule) => rule.label).join(' · ')}
              </div>
            </Alert>

            {!generateRandom && (
              <Form.Group className="mb-3">
                <Form.Label>Password (same for all users)</Form.Label>
                <InputGroup>
                  <Form.Control
                    type="text"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter password"
                    required={!generateRandom}
                    minLength={8}
                    isInvalid={Boolean(manualPasswordError)}
                    isValid={isStrongPassword(password)}
                  />
                  <Button
                    variant="outline-secondary"
                    onClick={() => setPassword(generateStrongPassword())}
                  >
                    Generate
                  </Button>
                  {manualPasswordError && (
                    <Form.Control.Feedback type="invalid">
                      {manualPasswordError}
                    </Form.Control.Feedback>
                  )}
                </InputGroup>
                <div className="mt-2 small">
                  {PASSWORD_RULES.map((rule, i) => (
                    <div key={i} className={rule.test(password) ? 'text-success' : 'text-danger'}>
                      {rule.test(password) ? '✓' : '●'} {rule.label}
                    </div>
                  ))}
                </div>
              </Form.Group>
            )}

            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Force password change on first login"
                checked={forceChange}
                onChange={(e) => setForceChange(e.target.checked)}
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Grant admin privileges"
                checked={isAdmin}
                onChange={(e) => setIsAdmin(e.target.checked)}
              />
            </Form.Group>

          </Form>
        ) : (
          <div>
            {(() => {
              const newUsers = createdUsers.filter(u => u.status === 'created');
              const existedUsers = createdUsers.filter(u => u.status === 'existed');
              const failedPw = newUsers.filter(u => !u.passwordSet).length;
              return (
                <>
                  {newUsers.length > 0 && (
                    <Alert variant="success" className="py-2">
                      {newUsers.length} user(s) created successfully.
                    </Alert>
                  )}
                  {existedUsers.length > 0 && (
                    <Alert variant="warning" className="py-2">
                      {existedUsers.length} user(s) already existed and were skipped (no changes made).
                    </Alert>
                  )}
                  {failedPw > 0 && (
                    <Alert variant="danger" className="py-2">
                      {failedPw} newly created user(s) failed to set password.
                    </Alert>
                  )}
                  {newUsers.length === 0 && existedUsers.length > 0 && (
                    <Alert variant="info" className="py-2">
                      No new users were created. All usernames already exist in the system.
                    </Alert>
                  )}
                </>
              );
            })()}
            {error && (
              <Alert variant="warning" className="py-2">
                <small>{error.split('\n').map((line, i) => (
                  <div key={i}>{line}</div>
                ))}</small>
              </Alert>
            )}
            <p className="text-muted">
              Copy the credentials below and share them with the users:
            </p>
            <div className="table-responsive">
              <table className="table table-sm table-bordered">
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Password</th>
                    <th style={{ width: '120px' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {createdUsers.map((user) => (
                    <tr key={user.username}>
                      <td><code>{user.username}</code></td>
                      <td>
                        {user.passwordSet ? (
                          <code>{user.password}</code>
                        ) : user.status === 'existed' ? (
                          <span className="text-muted">-</span>
                        ) : (
                          <span className="text-danger">(failed)</span>
                        )}
                      </td>
                      <td>
                        {user.status === 'created' ? (
                          user.passwordSet ? (
                            <Badge bg="success">New</Badge>
                          ) : (
                            <Badge bg="danger">PW failed</Badge>
                          )
                        ) : user.status === 'existed' ? (
                          <Badge bg="secondary">Skipped</Badge>
                        ) : (
                          <Badge bg="danger">Failed</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {forceChange && (
              <Alert variant="info" className="mt-3">
                Users will be prompted to change their password on first login.
              </Alert>
            )}
          </div>
        )}
      </Modal.Body>
      <Modal.Footer>
        {step === 'input' ? (
          <>
            <Button variant="secondary" onClick={handleClose}>
              Cancel
            </Button>
            <Button
              variant="dark"
              onClick={handleSubmit}
              disabled={!canSubmit}
            >
              {loading ? (
                <>
                  <Spinner animation="border" size="sm" className="me-1" />
                  Creating...
                </>
              ) : (
                'Create Users'
              )}
            </Button>
          </>
        ) : (
          <>
            <Button variant="outline-primary" onClick={copyToClipboard}>
              <i className="bi bi-clipboard me-1"></i> Copy
            </Button>
            <Button variant="outline-primary" onClick={downloadCsv}>
              <i className="bi bi-download me-1"></i> CSV
            </Button>
            <Button variant="dark" onClick={handleClose}>
              Done
            </Button>
          </>
        )}
      </Modal.Footer>
    </Modal>
  );
}
