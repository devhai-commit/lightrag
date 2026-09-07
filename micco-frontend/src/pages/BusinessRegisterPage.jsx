import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTheme } from '../context/ThemeContext';
import { resolveApiBase } from '../utils/apiBase';
import { Building2, User, Mail, Phone, Lock, ShieldCheck, ArrowRight, Sun, Moon, CheckCircle2, FileText } from 'lucide-react';

const API_BASE = `${resolveApiBase()}/api`;

export default function BusinessRegisterPage() {
    const { isDark, toggleTheme } = useTheme();
    const [submitted, setSubmitted] = useState(false);

    return (
        <div className="min-h-screen flex items-center justify-center bg-[#2a5298] relative overflow-hidden px-4 py-10">
            <div className="absolute inset-0 pointer-events-none overflow-hidden">
                <div className="absolute -bottom-20 -left-20 w-[420px] h-[420px] rounded-full animate-float"
                    style={{
                        background: 'radial-gradient(circle at 35% 35%, #5b8def 0%, #1e3a8a 60%, #0f1f4e 100%)',
                        boxShadow: '0 0 80px rgba(30, 58, 138, 0.5), inset 0 -20px 60px rgba(0,0,0,0.3)',
                    }}
                />
                <div className="absolute -top-10 right-[15%] w-[240px] h-[240px] rounded-full opacity-60 animate-float-delayed"
                    style={{
                        background: 'radial-gradient(circle at 35% 35%, #87b4f9 0%, #4c7bd4 60%, #2a5298 100%)',
                        boxShadow: '0 0 50px rgba(79, 70, 229, 0.2)',
                    }}
                />
            </div>

            <div className="relative z-10 w-full max-w-lg bg-white dark:bg-gray-900 rounded-3xl shadow-2xl shadow-black/30 p-8 sm:p-10">
                <button onClick={toggleTheme}
                    className="absolute top-5 right-5 p-2 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 transition-all">
                    {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
                </button>

                {submitted ? <SuccessPanel /> : <BusinessForm onSuccess={() => setSubmitted(true)} />}
            </div>
        </div>
    );
}

function SuccessPanel() {
    return (
        <div className="text-center py-6">
            <div className="w-16 h-16 rounded-full bg-emerald-50 dark:bg-emerald-500/10 flex items-center justify-center mx-auto mb-5">
                <CheckCircle2 className="w-8 h-8 text-emerald-500" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">Đăng ký thành công</h2>
            <p className="text-gray-500 dark:text-gray-400 text-sm leading-relaxed mb-8">
                Đội ngũ Micco sẽ xem xét và duyệt tài khoản của bạn trong thời gian sớm nhất.
                Bạn sẽ có thể đăng nhập ngay sau khi tài khoản được duyệt.
            </p>
            <Link to="/login"
                className="inline-flex items-center justify-center gap-2 px-8 py-3 rounded-2xl font-bold text-white text-sm tracking-wide transition-all duration-300"
                style={{ background: 'linear-gradient(135deg, #1e3a8a 0%, #2a5298 50%, #4F46E5 100%)', boxShadow: '0 8px 32px rgba(30, 58, 138, 0.35)' }}>
                Quay lại đăng nhập <ArrowRight className="w-4 h-4" />
            </Link>
        </div>
    );
}

const FIELD_ICON_WRAPPER = 'absolute left-4 top-1/2 -translate-y-1/2 w-9 h-9 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center group-focus-within:bg-primary-600/10 dark:group-focus-within:bg-primary-600/20 transition-colors';
const FIELD_ICON_CLASS = 'w-4 h-4 text-gray-400 group-focus-within:text-primary-600 dark:group-focus-within:text-primary-400 transition-colors';
const FIELD_INPUT_CLASS = 'w-full pl-16 pr-5 py-3 rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 text-gray-900 dark:text-white placeholder-gray-400 outline-none focus:border-primary-600 focus:ring-2 focus:ring-primary-600/10 dark:focus:border-secondary-400 dark:focus:ring-secondary-400/10 transition-all text-sm';

function BusinessForm({ onSuccess }) {
    const [form, setForm] = useState({
        company_name: '', tax_code: '', contact_name: '', email: '',
        phone: '', industry: '', password: '', confirm_password: '',
    });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
    const passwordsMatch = !form.confirm_password || form.password === form.confirm_password;

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (form.company_name.trim().length < 2) return setError('Tên công ty phải có ít nhất 2 ký tự');
        if (form.contact_name.trim().length < 2) return setError('Tên người liên hệ phải có ít nhất 2 ký tự');
        if (!form.phone.trim()) return setError('Vui lòng nhập số điện thoại');
        if (form.password.length < 6) return setError('Mật khẩu phải có ít nhất 6 ký tự');
        if (!passwordsMatch) return setError('Mật khẩu xác nhận không khớp');

        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/auth/register-business`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    company_name: form.company_name.trim(),
                    contact_name: form.contact_name.trim(),
                    email: form.email.trim(),
                    password: form.password,
                    phone: form.phone.trim(),
                    tax_code: form.tax_code.trim() || null,
                    industry: form.industry.trim() || null,
                }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                setError(err.detail || 'Đăng ký thất bại');
                setLoading(false);
                return;
            }
            onSuccess();
        } catch {
            setError('Không thể kết nối máy chủ');
            setLoading(false);
        }
    };

    return (
        <div>
            <div className="flex items-center gap-2 mb-1">
                <Building2 className="w-5 h-5 text-primary-600 dark:text-secondary-400" />
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Đăng ký cho Doanh nghiệp</h2>
            </div>
            <p className="text-gray-500 dark:text-gray-400 text-sm mb-6">
                Tạo tài khoản để trao đổi với đội ngũ Micco về giải pháp phù hợp cho doanh nghiệp bạn.
            </p>

            {error && (
                <div className="mb-4 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 text-sm font-medium">
                    {error}
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-3.5">
                <div className="relative group">
                    <div className={FIELD_ICON_WRAPPER}><Building2 className={FIELD_ICON_CLASS} /></div>
                    <input value={form.company_name} onChange={set('company_name')} placeholder="Tên công ty *" className={FIELD_INPUT_CLASS} required />
                </div>

                <div className="grid grid-cols-2 gap-3">
                    <div className="relative group">
                        <div className={FIELD_ICON_WRAPPER}><FileText className={FIELD_ICON_CLASS} /></div>
                        <input value={form.tax_code} onChange={set('tax_code')} placeholder="Mã số thuế" className={FIELD_INPUT_CLASS} />
                    </div>
                    <div className="relative group">
                        <div className={FIELD_ICON_WRAPPER}><Building2 className={FIELD_ICON_CLASS} /></div>
                        <input value={form.industry} onChange={set('industry')} placeholder="Ngành nghề" className={FIELD_INPUT_CLASS} />
                    </div>
                </div>

                <div className="relative group">
                    <div className={FIELD_ICON_WRAPPER}><User className={FIELD_ICON_CLASS} /></div>
                    <input value={form.contact_name} onChange={set('contact_name')} placeholder="Người liên hệ *" className={FIELD_INPUT_CLASS} required />
                </div>

                <div className="grid grid-cols-2 gap-3">
                    <div className="relative group">
                        <div className={FIELD_ICON_WRAPPER}><Mail className={FIELD_ICON_CLASS} /></div>
                        <input type="email" value={form.email} onChange={set('email')} placeholder="Email *" className={FIELD_INPUT_CLASS} required />
                    </div>
                    <div className="relative group">
                        <div className={FIELD_ICON_WRAPPER}><Phone className={FIELD_ICON_CLASS} /></div>
                        <input value={form.phone} onChange={set('phone')} placeholder="Số điện thoại *" className={FIELD_INPUT_CLASS} required />
                    </div>
                </div>

                <div className="relative group">
                    <div className={FIELD_ICON_WRAPPER}><Lock className={FIELD_ICON_CLASS} /></div>
                    <input type="password" value={form.password} onChange={set('password')} placeholder="Mật khẩu *" minLength={6} className={FIELD_INPUT_CLASS} required />
                </div>

                <div className="relative group">
                    <div className={`absolute left-4 top-1/2 -translate-y-1/2 w-9 h-9 rounded-xl flex items-center justify-center transition-colors ${!passwordsMatch ? 'bg-red-100 dark:bg-red-900/30' : 'bg-gray-100 dark:bg-gray-800 group-focus-within:bg-primary-600/10 dark:group-focus-within:bg-primary-600/20'}`}>
                        <ShieldCheck className={`w-4 h-4 transition-colors ${!passwordsMatch ? 'text-red-500' : 'text-gray-400 group-focus-within:text-primary-600 dark:group-focus-within:text-primary-400'}`} />
                    </div>
                    <input type="password" value={form.confirm_password} onChange={set('confirm_password')} placeholder="Xác nhận mật khẩu *"
                        className={`${FIELD_INPUT_CLASS} ${!passwordsMatch ? '!border-red-400' : ''}`} required />
                    {!passwordsMatch && <p className="text-xs text-red-500 mt-1 ml-1 font-medium">Mật khẩu không khớp</p>}
                </div>

                <button type="submit" disabled={loading || !passwordsMatch}
                    className="w-full py-3.5 rounded-2xl font-bold text-white text-sm tracking-wide transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed relative overflow-hidden group"
                    style={{ background: 'linear-gradient(135deg, #1e3a8a 0%, #2a5298 50%, #4F46E5 100%)', boxShadow: '0 8px 32px rgba(30, 58, 138, 0.35)' }}>
                    <div className="absolute inset-0 bg-white/10 translate-y-full group-hover:translate-y-0 transition-transform duration-500" />
                    {loading
                        ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto" />
                        : <span className="relative z-10 flex items-center justify-center gap-2">Gửi đăng ký <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" /></span>
                    }
                </button>
            </form>

            <p className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
                Đã có tài khoản?{' '}
                <Link to="/login" className="font-bold text-primary-600 dark:text-secondary-400 hover:underline">Đăng nhập</Link>
            </p>
        </div>
    );
}
