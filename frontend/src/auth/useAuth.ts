import { useContext } from 'react';
import { AuthContext } from './context';
import type { AuthContextValue } from './context';

/** Access the current session. Kept out of the provider file so that module
 *  only exports components and Fast Refresh keeps working. */
export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth 必须在 AuthProvider 内使用');
  }
  return context;
};
