/**
 * The portal's auth context object and its consumer hook.
 *
 * Split out from BusinessAuthProvider.jsx so that file exports only a
 * component — react-refresh needs that to hot-reload the provider without
 * dropping the session on every edit.
 */
import { createContext, useContext } from 'react';

export const BusinessAuthContext = createContext(null);

export function useBusinessAuth() {
    const context = useContext(BusinessAuthContext);
    if (!context) {
        throw new Error('useBusinessAuth must be used inside BusinessAuthProvider');
    }
    return context;
}
