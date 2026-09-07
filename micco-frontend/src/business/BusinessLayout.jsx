/**
 * BusinessLayout — the portal shell.
 *
 * Not DashboardLayout: that file hardcodes the internal navigation (documents,
 * approvals, workspaces, knowledge graph), none of which exists for a customer.
 * This shell is deliberately almost empty — a slim masthead and a footer — so
 * the conversation is the whole page.
 */
import { Outlet } from 'react-router-dom';
import { Building2, LogOut } from 'lucide-react';

import { useBusinessAuth } from './businessAuthContext';

export default function BusinessLayout() {
    const { user, logout } = useBusinessAuth();

    return (
        <div className="micco-portal p-grain min-h-screen flex flex-col">
            <header className="relative z-10 border-b border-[var(--p-line)] bg-[var(--p-surface)]/70 backdrop-blur-sm">
                <div className="mx-auto max-w-[var(--p-measure)] px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
                    <div className="flex items-baseline gap-3 min-w-0">
                        <span className="p-display text-lg sm:text-xl text-[var(--p-ink)] tracking-tight">
                            MICCO
                        </span>
                        <span className="hidden sm:inline w-px h-4 bg-[var(--p-line-strong)]" aria-hidden="true" />
                        <span className="p-eyebrow truncate">Cổng doanh nghiệp</span>
                    </div>

                    <div className="flex items-center gap-2 sm:gap-4 min-w-0">
                        {user?.company_name && (
                            <span className="hidden md:flex items-center gap-2 min-w-0 text-sm text-[var(--p-ink-soft)]">
                                <Building2 className="w-3.5 h-3.5 shrink-0 text-[var(--p-muted)]" />
                                <span className="truncate max-w-[16rem]">{user.company_name}</span>
                            </span>
                        )}
                        <button type="button" onClick={logout} className="p-btn-ghost">
                            <LogOut className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">Đăng xuất</span>
                        </button>
                    </div>
                </div>
            </header>

            <main className="relative z-10 flex-1 flex flex-col min-h-0">
                <Outlet />
            </main>

            <footer className="relative z-10 border-t border-[var(--p-line)] px-4 sm:px-6 py-4">
                <p className="mx-auto max-w-[var(--p-measure)] text-xs leading-relaxed text-[var(--p-muted)]">
                    Thông tin trên cổng này mang tính tham khảo. Giá và điều khoản hợp đồng
                    do đội ngũ kinh doanh Micco xác nhận.
                </p>
            </footer>
        </div>
    );
}
