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

import { useState, useMemo } from 'react';
import { Modal, Button, Form, Alert, Spinner, InputGroup, Badge } from 'react-bootstrap';
import * as api from '@auplc/shared';
import { generateStrongPassword, getPasswordError, isStrongPassword, PASSWORD_RULES } from '@auplc/shared';

interface Props {
  show: boolean;
  usernames: string[];
  onHide: () => void;
}

interface PasswordResult {
  username: string;
  password: string;
  status: 'success' | 'failed';
  error?: string;
}

export function BatchPasswordModal({ show, usernames, onHide }: Props) {
  const [generateRandom, setGenerateRandom] = useState(true);
  const [password, setPassword] = useState('');
  const [forceChange, setForceChange] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<PasswordResult[]>([]);
  const [step, setStep] = useState<'input' | 'result'>('input');

  const handleSubmit = async () => {
    setError(null);

    const passwordError = generateRandom ? null : getPasswordError(password);
    if (passwordError) {
      setError(passwordError);
      return;
    }

    setLoading(true);

    try {
      const entries = usernames.map(username => ({
        username,
        password: generateRandom ? generateStrongPassword() : password,
      }));

      const response = await api.batchSetPasswords(entries, forceChange);

      const pwResults: PasswordResult[] = entries.map(entry => {
        const r = response.results.find(r => r.username === entry.username);
        return {
          username: entry.username,
          password: entry.password,
          status: r?.status === 'success' ? 'success' as const : 'failed' as const,
          error: r?.error,
        };
      });

      setResults(pwResults);
      setStep('result');

      if (response.failed > 0) {
        setError(`${response.failed} password(s) failed to set`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set passwords');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setGenerateRandom(true);
    setPassword('');
    setForceChange(true);
    setError(null);
    setResults([]);
    setStep('input');
    onHide();
  };

  const successResults = useMemo(
    () => results.filter(r => r.status === 'success'),
    [results]
  );

  const copyToClipboard = () => {
    const text = successResults
      .map(r => `${r.username}\t${r.password}`)
      .join('\n');
    navigator.clipboard.writeText(text);
  };

  const downloadCsv = () => {
    const header = 'username,password,status\n';
    const rows = results
      .map(r => `${r.username},${r.status === 'success' ? r.password : ''},${r.status}`)
      .join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `passwords-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const manualPasswordError = generateRandom ? null : getPasswordError(password);
  const canSubmit = !loading && (generateRandom || isStrongPassword(password));

  return (
    <Modal show={show} onHide={handleClose} size="lg">
      <Modal.Header closeButton>
        <Modal.Title>
          {step === 'input' ? `Reset Passwords (${usernames.length} users)` : 'Password Reset Results'}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {step === 'input' ? (
          <div>
            {error && <Alert variant="danger">{error}</Alert>}

            <Alert variant="warning" className="py-2">
              This will reset passwords for {usernames.length} selected user(s).
              Users will need to use the new passwords to log in.
            </Alert>

            <div className="mb-3">
              <strong>Users:</strong>{' '}
              {usernames.slice(0, 10).map(name => (
                <Badge key={name} bg="secondary" className="me-1">{name}</Badge>
              ))}
              {usernames.length > 10 && (
                <Badge bg="secondary">+{usernames.length - 10} more</Badge>
              )}
            </div>

            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Generate random passwords (unique per user)"
                checked={generateRandom}
                onChange={(e) => setGenerateRandom(e.target.checked)}
              />
            </Form.Group>

            <Alert variant="info" className="py-2">
              <div className="fw-semibold mb-1">Passwords must meet all native-login rules.</div>
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
                label="Force password change on next login"
                checked={forceChange}
                onChange={(e) => setForceChange(e.target.checked)}
              />
            </Form.Group>
          </div>
        ) : (
          <div>
            {(() => {
              const successCount = successResults.length;
              const failedCount = results.length - successCount;
              return (
                <>
                  {successCount > 0 && (
                    <Alert variant="success" className="py-2">
                      {successCount} password(s) reset successfully.
                    </Alert>
                  )}
                  {failedCount > 0 && (
                    <Alert variant="danger" className="py-2">
                      {failedCount} password(s) failed to set.
                    </Alert>
                  )}
                </>
              );
            })()}
            {error && (
              <Alert variant="warning" className="py-2">
                <small>{error}</small>
              </Alert>
            )}
            <p className="text-muted">
              Copy the new credentials and share them with the users:
            </p>
            <div className="table-responsive">
              <table className="table table-sm table-bordered">
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Password</th>
                    <th style={{ width: '80px' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => (
                    <tr key={r.username}>
                      <td><code>{r.username}</code></td>
                      <td>
                        {r.status === 'success' ? (
                          <code>{r.password}</code>
                        ) : (
                          <span className="text-danger">(failed)</span>
                        )}
                      </td>
                      <td>
                        {r.status === 'success' ? (
                          <Badge bg="success">OK</Badge>
                        ) : (
                          <Badge bg="danger" title={r.error}>Failed</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {forceChange && (
              <Alert variant="info" className="mt-3">
                Users will be prompted to change their password on next login.
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
                  Resetting...
                </>
              ) : (
                'Reset Passwords'
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
