import { describe, expect, it } from 'vitest';
import { isMainNavActive } from './mainNavActive';

describe('isMainNavActive', () => {
  it('treats /qa-studio and subpaths as QA Studio', () => {
    expect(isMainNavActive('/qa-studio', '/qa-studio')).toBe(true);
    expect(isMainNavActive('/qa-studio/', '/qa-studio')).toBe(true);
    expect(isMainNavActive('/qa-studio/dashboard', '/qa-studio')).toBe(true);
    expect(isMainNavActive('/qa-studio/authoring', '/qa-studio')).toBe(true);
    expect(isMainNavActive('/chat', '/qa-studio')).toBe(false);
  });

  it('uses exact match for other nav items', () => {
    expect(isMainNavActive('/chat', '/chat')).toBe(true);
    expect(isMainNavActive('/chat/', '/chat')).toBe(false);
  });
});
