/**
 * BusinessAuthGate — the portal's route guard.
 *
 * The portal's counterpart to ProtectedRoute/PublicOnlyRoute in App.jsx, which
 * both read the internal AuthContext and redirect to internal routes.
 *
 * `anonymousOnly` inverts it for the login page, so an already signed-in
 * customer lands on the conversation instead of a form.
 */
import { Navigate, Outlet } from 'react-router-dom';

import { useBusinessAuth } from './businessAuthContext';

function PortalSpinner() {
    return (
        <div className="micco-portal min-h-screen flex items-center justify-center">
            <div
                className="w-6 h-6 border-2 border-[var(--p-accent)] border-t-transparent rounded-full animate-spin"
                role="status"
                aria-label="Đang tải"
            />
        </div>
    );
}

export default function BusinessAuthGate({ anonymousOnly = false, children }) {
    const { isAuthenticated, loading } = useBusinessAuth();

    if (loading) return <PortalSpinner />;

    if (anonymousOnly) {
        return isAuthenticated ? <Navigate to="/business/chat" replace /> : (children ?? <Outlet />);
    }

    if (!isAuthenticated) return <Navigate to="/business/login" replace />;
    return children ?? <Outlet />;
}
