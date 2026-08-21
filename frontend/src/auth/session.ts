/**
 * Session token storage and helpers.
 *
 * The token is kept in sessionStorage so it is dropped when the tab closes and
 * is not shared with other tabs of the same origin.
 */

export interface AuthUser {
  userId: number;
  username: string;
  displayName: string;
  roleCode: string;
  capabilities: string[];
}

const TOKEN_KEY = 'ontology.session.token';
const USER_KEY = 'ontology.session.user';

export const getToken = (): string => sessionStorage.getItem(TOKEN_KEY) ?? '';

export const getStoredUser = (): AuthUser | null => {
  const raw = sessionStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
};

export const storeSession = (token: string, user: AuthUser): void => {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
};

export const clearSession = (): void => {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
};

export const hasCapability = (user: AuthUser | null, capability: string): boolean =>
  Boolean(user?.capabilities?.includes(capability));

export const CAPABILITIES = {
  read: 'platform:read',
  write: 'platform:write',
  review: 'governance:review',
  publish: 'governance:publish',
  execute: 'automation:execute',
  admin: 'platform:admin',
} as const;
