/**
 * BusinessPortal — the /business/* route tree, self-contained.
 *
 * Mounted in App.jsx outside ProtectedRoute and PublicOnlyRoute on purpose:
 *
 * - ProtectedRoute would demand an internal session.
 * - PublicOnlyRoute would bounce a customer to /dashboard whenever an employee
 *   happened to be signed in on the same browser.
 *
 * Everything below it sits inside BusinessAuthProvider, so the internal
 * AuthContext is never consulted here.
 */
import { Navigate, Route, Routes } from 'react-router-dom';

import BusinessAuthGate from './BusinessAuthGate';
import BusinessChatPage from './BusinessChatPage';
import BusinessLayout from './BusinessLayout';
import BusinessLoginPage from './BusinessLoginPage';
import BusinessAuthProvider from './BusinessAuthProvider';
import './business.css';

export default function BusinessPortal() {
    return (
        <BusinessAuthProvider>
            <Routes>
                <Route path="login" element={<BusinessAuthGate anonymousOnly><BusinessLoginPage /></BusinessAuthGate>} />

                <Route element={<BusinessAuthGate><BusinessLayout /></BusinessAuthGate>}>
                    <Route path="chat" element={<BusinessChatPage />} />
                </Route>

                <Route path="*" element={<Navigate to="/business/chat" replace />} />
            </Routes>
        </BusinessAuthProvider>
    );
}
