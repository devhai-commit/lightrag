/**
 * BusinessLoginPage — the portal's own front door.
 *
 * Internal /api/auth/login rejects business accounts with a 403 pointing here,
 * so this is the only place an approved customer can sign in. The two states an
 * Admin can leave an account in — pending and rejected — arrive as that 403's
 * message and are shown as-is rather than flattened into "login failed".
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Lock, Mail } from 'lucide-react';

import { useBusinessAuth } from './businessAuthContext';

export default function BusinessLoginPage() {
    const { login } = useBusinessAuth();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const handleSubmit = async (event) => {
        event.preventDefault();
        setError('');
        setSubmitting(true);

        const result = await login(email.trim(), password);
        if (!result.success) {
            setError(result.error || 'Đăng nhập thất bại');
            setSubmitting(false);
        }
        // On success the router swaps this page out, so there is no state to
        // reset — setting it would warn about an unmounted component.
    };

    return (
        <div className="micco-portal p-grain min-h-screen flex flex-col">
            <div className="relative z-10 flex-1 grid lg:grid-cols-[1.1fr_1fr]">
                {/* Editorial half. Hidden on small screens, where the form is
                    the only thing worth the space. */}
                <section className="hidden lg:flex flex-col justify-between border-r border-[var(--p-line)] px-12 xl:px-20 py-16">
                    <span className="p-display text-xl text-[var(--p-ink)]">MICCO</span>

                    <div className="max-w-xl">
                        <p className="p-eyebrow mb-6">Cổng doanh nghiệp</p>
                        <h1 className="p-display text-5xl xl:text-6xl leading-[1.05] text-[var(--p-ink)] mb-8">
                            Tra cứu sản phẩm và điều khoản hợp đồng, trực tiếp từ tài liệu Micco.
                        </h1>
                        <p className="text-[0.9375rem] leading-relaxed text-[var(--p-ink-soft)] max-w-md">
                            Đặt câu hỏi bằng tiếng Việt về vật liệu nổ công nghiệp, dịch vụ nổ mìn
                            và điều kiện hợp tác. Câu trả lời chỉ dựa trên tài liệu Micco đã công bố
                            cho khách hàng.
                        </p>
                    </div>

                    <p className="text-xs text-[var(--p-muted)]">
                        Tài khoản nhân sự Micco vui lòng dùng{' '}
                        <Link to="/login" className="underline decoration-[var(--p-line-strong)] underline-offset-2 hover:text-[var(--p-accent)]">
                            cổng nội bộ
                        </Link>.
                    </p>
                </section>

                {/* Form half */}
                <section className="flex items-center justify-center px-4 sm:px-8 py-12">
                    <div className="w-full max-w-sm">
                        <p className="p-eyebrow mb-3 lg:hidden">Micco · Cổng doanh nghiệp</p>
                        <h2 className="p-display text-3xl text-[var(--p-ink)] mb-2">Đăng nhập</h2>
                        <p className="text-sm text-[var(--p-ink-soft)] mb-8">
                            Dùng email doanh nghiệp bạn đã đăng ký.
                        </p>

                        {error && (
                            <div
                                role="alert"
                                className="mb-6 border-l-2 border-[var(--p-danger)] bg-[var(--p-surface)] px-4 py-3 text-sm text-[var(--p-danger)]"
                            >
                                {error}
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="space-y-5">
                            <div>
                                <label htmlFor="business-email" className="p-eyebrow block mb-2">
                                    Email
                                </label>
                                <div className="relative">
                                    <Mail className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--p-muted)]" aria-hidden="true" />
                                    <input
                                        id="business-email"
                                        type="email"
                                        autoComplete="email"
                                        required
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        placeholder="lienhe@congty.vn"
                                        className="p-field !pl-10"
                                    />
                                </div>
                            </div>

                            <div>
                                <label htmlFor="business-password" className="p-eyebrow block mb-2">
                                    Mật khẩu
                                </label>
                                <div className="relative">
                                    <Lock className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--p-muted)]" aria-hidden="true" />
                                    <input
                                        id="business-password"
                                        type="password"
                                        autoComplete="current-password"
                                        required
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        placeholder="••••••••"
                                        className="p-field !pl-10"
                                    />
                                </div>
                            </div>

                            <button type="submit" disabled={submitting} className="p-btn w-full">
                                {submitting ? 'Đang đăng nhập...' : 'Đăng nhập'}
                                {!submitting && <ArrowRight className="w-4 h-4" />}
                            </button>
                        </form>

                        <div className="mt-8 pt-6 border-t border-[var(--p-line)] space-y-2">
                            <p className="text-sm text-[var(--p-ink-soft)]">
                                Chưa có tài khoản?{' '}
                                <Link to="/register-business" className="font-semibold text-[var(--p-accent)] hover:underline underline-offset-2">
                                    Đăng ký cho doanh nghiệp
                                </Link>
                            </p>
                            <p className="text-xs text-[var(--p-muted)] lg:hidden">
                                Nhân sự Micco vui lòng dùng{' '}
                                <Link to="/login" className="underline underline-offset-2">cổng nội bộ</Link>.
                            </p>
                        </div>
                    </div>
                </section>
            </div>
        </div>
    );
}
