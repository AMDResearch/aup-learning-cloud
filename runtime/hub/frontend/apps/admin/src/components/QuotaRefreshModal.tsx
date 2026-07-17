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

import { useState } from 'react';
import { Modal, Button, Form, Alert, Spinner } from 'react-bootstrap';
import { adminApiRequest } from '@auplc/shared';

interface Props {
  show: boolean;
  onHide: () => void;
  onSuccess: () => void;
}

export function QuotaRefreshModal({ show, onHide, onSuccess }: Props) {
  const [amount, setAmount] = useState('100');
  const [action, setAction] = useState<'add' | 'set'>('add');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ updated: number; skipped: number } | null>(null);

  const handleRefresh = async () => {
    const numAmount = parseInt(amount);
    if (isNaN(numAmount) || numAmount <= 0) {
      setError('Amount must be a positive number');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await adminApiRequest<{ updated: number; skipped: number }>('/quota/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rule_name: 'manual-refresh',
          action,
          amount: numAmount,
          targets: {},
        }),
      });
      setResult(res);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh quota');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setError(null);
    setResult(null);
    onHide();
  };

  return (
    <Modal show={show} onHide={handleClose} centered>
      <Modal.Header closeButton>
        <Modal.Title>Refresh Quota</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p className="text-body-secondary" style={{ fontSize: '0.85rem' }}>
          Apply a quota adjustment to all users at once.
        </p>

        {error && <Alert variant="danger">{error}</Alert>}
        {result && (
          <Alert variant="success">
            Refresh complete: {result.updated} updated, {result.skipped} skipped
          </Alert>
        )}

        <Form.Group className="mb-3">
          <Form.Label>Action</Form.Label>
          <Form.Select value={action} onChange={e => setAction(e.target.value as 'add' | 'set')}>
            <option value="add">Add to current balance</option>
            <option value="set">Set to exact amount</option>
          </Form.Select>
        </Form.Group>

        <Form.Group className="mb-3">
          <Form.Label>Amount</Form.Label>
          <Form.Control
            type="number"
            min={1}
            value={amount}
            onChange={e => setAmount(e.target.value)}
          />
          <Form.Text className="text-muted">
            {action === 'add'
              ? 'Credits to add to each user\'s current balance'
              : 'Set every user\'s balance to this value'}
          </Form.Text>
        </Form.Group>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={handleClose} disabled={loading}>
          Close
        </Button>
        <Button variant="dark" onClick={handleRefresh} disabled={loading}>
          {loading ? <><Spinner animation="border" size="sm" className="me-1" /> Refreshing...</> : 'Apply to All Users'}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
