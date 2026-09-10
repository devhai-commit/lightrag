/**
 * BusinessAuthProvider — session state for external business customers.
 *
 * Separate from src/context/AuthContext.jsx, not a variant of it:
 *
 * - Its own storage key (see businessApi.js), so a customer signing in here
 *   cannot overwrite an employee's session in the same browser.
 * - No VITE_SKIP_AUTH branch. The dev bypass hands out a mock Admin, and the
 *   backend rejects the `dev-skip` token on every /business/* endpoint, so
 *   honouring it here would only produce a UI signed in as nobody.
 * - No approval polling. That belongs to staff.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import { BusinessAuthContext } from './businessAuthContext';
import {
    businessAuthApi,
    clearBusinessToken,
    getBusinessToken,
    setBusinessToken,
} from './businessApi';

export default function BusinessAuthProvider({ children }) {
    const [user, setUser] = useState(null);
    // Starts true only when there is a token to verify, so the no-session case
    // renders the login page immediately instead of flashing a spinner.
    const [loading, setLoading] = useState(() => Boolean(getBusinessToken()));

    // Restore the session on mount. A stored token the server no longer accepts
    // is cleared by businessApi, so a revoked approval takes effect on the next
    // page load rather than lingering until the token expires.
    useEffect(() => {
        if (!getBusinessToken()) return;

        let cancelled = false;
        businessAuthApi
            .me()
            .then((profile) => { if (!cancelled) setUser(profile); })
            .catch(() => { if (!cancelled) setUser(null); })
            .finally(() => { if (!cancelled) setLoading(false); });

        return () => { cancelled = true; };
    }, []);

    const login = useCallback(async (email, password) => {
        try {
            const data = await businessAuthApi.login(email, password);
            setBusinessToken(data.access_token);
            setUser(data.user);
            return { success: true };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }, []);

    const logout = useCallback(() => {
        clearBusinessToken();
        setUser(null);
    }, []);

    const value = useMemo(
        () => ({ user, loading, isAuthenticated: Boolean(user), login, logout }),
        [user, loading, login, logout],
    );

    return (
        <BusinessAuthContext.Provider value={value}>
            {children}
        </BusinessAuthContext.Provider>
    );
}
