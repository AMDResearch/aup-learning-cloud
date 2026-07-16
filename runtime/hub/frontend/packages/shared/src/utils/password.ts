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

export interface PasswordRule {
  label: string;
  test: (password: string) => boolean;
}

const UPPERCASE = "ABCDEFGHJKLMNPQRSTUVWXYZ";
const LOWERCASE = "abcdefghijkmnpqrstuvwxyz";
const DIGITS = "23456789";
const SPECIAL = "!@#$%^&*_+-=";

export const PASSWORD_RULES: PasswordRule[] = [
  { test: (password: string) => password.length >= 8, label: "At least 8 characters" },
  { test: (password: string) => /[A-Z]/.test(password), label: "One uppercase letter" },
  { test: (password: string) => /[a-z]/.test(password), label: "One lowercase letter" },
  { test: (password: string) => /\d/.test(password), label: "One digit" },
  {
    test: (password: string) => /[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?`~]/.test(password),
    label: "One special character",
  },
];

function randomIndex(length: number): number {
  if (globalThis.crypto?.getRandomValues) {
    const value = new Uint32Array(1);
    globalThis.crypto.getRandomValues(value);
    return value[0] % length;
  }
  throw new Error("Secure random password generation is not available in this browser");
}

function pick(chars: string): string {
  return chars[randomIndex(chars.length)];
}

function shuffle(chars: string[]): string[] {
  const result = [...chars];
  for (let i = result.length - 1; i > 0; i -= 1) {
    const j = randomIndex(i + 1);
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

export function getPasswordError(password: string): string | null {
  const failedRule = PASSWORD_RULES.find((rule) => !rule.test(password));
  return failedRule ? `Password requirement not met: ${failedRule.label}` : null;
}

export function isStrongPassword(password: string): boolean {
  return password.length > 0 && getPasswordError(password) === null;
}

export function generateStrongPassword(length = 16): string {
  const passwordLength = Math.max(length, 8);
  const all = UPPERCASE + LOWERCASE + DIGITS + SPECIAL;
  const chars = [pick(UPPERCASE), pick(LOWERCASE), pick(DIGITS), pick(SPECIAL)];

  while (chars.length < passwordLength) {
    chars.push(pick(all));
  }

  return shuffle(chars).join("");
}
