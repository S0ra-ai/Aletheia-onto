import { createContext } from 'react';
import type { AuthUser } from './session';

export interface AuthContextValue {
  user: AuthUser | null;
  initializing: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  can: (capability: string) => boolean;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
