# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Pydantic validation models for Quota API

import re
from enum import Enum

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class QuotaAction(str, Enum):
    """Allowed quota modification actions."""

    SET = "set"
    ADD = "add"
    DEDUCT = "deduct"
    SET_UNLIMITED = "set_unlimited"


class QuotaRefreshAction(str, Enum):
    """Allowed quota refresh actions."""

    ADD = "add"
    SET = "set"


class QuotaModifyRequest(BaseModel):
    """Request model for modifying user quota."""

    action: QuotaAction = Field(default=QuotaAction.SET, description="Action to perform")
    amount: int | None = Field(default=None, ge=-10_000_000, le=10_000_000, description="Quota amount")
    unlimited: bool | None = Field(default=None, description="Unlimited quota flag (for set_unlimited action)")
    description: str | None = Field(default=None, max_length=500, description="Optional description")

    @model_validator(mode="after")
    def validate_action_requirements(self) -> "QuotaModifyRequest":
        """Validate that required fields are present for each action."""
        if self.action == QuotaAction.SET_UNLIMITED:
            if self.unlimited is None:
                self.unlimited = True
        else:
            if self.amount is None:
                raise ValueError("amount is required for this action")
            if self.action == QuotaAction.SET and self.amount < 0:
                raise ValueError("amount cannot be negative for 'set' action")
            if self.action == QuotaAction.DEDUCT and self.amount <= 0:
                raise ValueError("amount must be positive for 'deduct' action")
        return self


class BatchQuotaUser(BaseModel):
    """User entry for batch quota operation."""

    username: str = Field(..., min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9._@:\-]+$")
    amount: int = Field(default=0, ge=-10_000_000, le=10_000_000)
    unlimited: bool | None = Field(default=None, description="Set unlimited quota (overrides amount)")


class BatchQuotaRequest(BaseModel):
    """Request model for batch quota operations."""

    users: list[BatchQuotaUser] = Field(..., max_length=1000, description="List of users (max 1000)")


class QuotaRefreshTargets(BaseModel):
    """Targeting rules for quota refresh."""

    includeUnlimited: bool = Field(default=False, description="Include users with unlimited quota")
    balanceBelow: int | None = Field(default=None, ge=0, le=10_000_000, description="Only if balance < this")
    balanceAbove: int | None = Field(default=None, ge=-10_000_000, le=10_000_000, description="Only if balance > this")
    includeUsers: list[str] | None = Field(default=None, max_length=1000, description="Whitelist of usernames")
    excludeUsers: list[str] | None = Field(default=None, max_length=1000, description="Blacklist of usernames")
    usernamePattern: str | None = Field(default=None, max_length=500, description="Regex pattern for usernames")

    @field_validator("includeUsers", "excludeUsers")
    @classmethod
    def validate_usernames(cls, v: list[str] | None) -> list[str] | None:
        """Validate that all usernames are valid."""
        if v is None:
            return v
        for username in v:
            if not username or not isinstance(username, str):
                raise ValueError("Username must be a non-empty string")
            if len(username) > 200:
                raise ValueError(f"Username '{username[:20]}...' too long (max 200 characters)")
            if not re.match(r"^[a-zA-Z0-9._@:\-]+$", username):
                raise ValueError(f"Username '{username}' contains invalid characters")
        return v

    @field_validator("usernamePattern")
    @classmethod
    def validate_regex(cls, v: str | None) -> str | None:
        """Validate that the pattern is a valid regex."""
        if v is None:
            return v
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e
        return v


class QuotaRefreshRequest(BaseModel):
    """Request model for quota refresh operation."""

    rule_name: str = Field(default="manual", max_length=100, description="Name of the refresh rule")
    action: QuotaRefreshAction = Field(default=QuotaRefreshAction.ADD, description="Refresh action (add or set)")
    amount: int = Field(..., ge=-10_000_000, le=10_000_000, description="Quota amount")
    max_balance: int | None = Field(default=None, ge=0, le=10_000_000, description="Maximum balance cap")
    min_balance: int | None = Field(default=None, ge=0, le=10_000_000, description="Minimum balance floor")
    targets: QuotaRefreshTargets = Field(default_factory=QuotaRefreshTargets, description="Targeting rules")


# Re-export ValidationError for convenience
__all__ = [
    "QuotaAction",
    "QuotaRefreshAction",
    "QuotaModifyRequest",
    "BatchQuotaUser",
    "BatchQuotaRequest",
    "QuotaRefreshTargets",
    "QuotaRefreshRequest",
    "ValidationError",
]
