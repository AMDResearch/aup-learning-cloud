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

import { afterEach, describe, expect, it, vi } from "vitest";

import { generateStrongPassword, getPasswordError, isStrongPassword } from "./password.js";

describe("password helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("accepts passwords that satisfy the native password policy", () => {
    expect(isStrongPassword("Valid-Password1")).toBe(true);
    expect(getPasswordError("Valid-Password1")).toBeNull();
  });

  it.each([
    ["Short1!", "At least 8 characters"],
    ["lowercase1!", "One uppercase letter"],
    ["UPPERCASE1!", "One lowercase letter"],
    ["NoDigits!", "One digit"],
    ["NoSpecial1", "One special character"],
  ])("rejects %s with %s", (password, label) => {
    expect(isStrongPassword(password)).toBe(false);
    expect(getPasswordError(password)).toBe(`Password requirement not met: ${label}`);
  });

  it("generates passwords that satisfy every rule", () => {
    for (let i = 0; i < 50; i += 1) {
      expect(isStrongPassword(generateStrongPassword())).toBe(true);
    }
  });

  it("does not fall back to non-secure random generation", () => {
    vi.stubGlobal("crypto", undefined);

    expect(() => generateStrongPassword()).toThrow("Secure random password generation is not available");
  });
});
