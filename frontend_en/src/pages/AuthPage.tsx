import { FormEvent, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Lock, Mail, Loader2, ArrowRight } from 'lucide-react';
import { useAuthStore } from '../stores/authStore';
import ThemeToggle from '../components/ThemeToggle';

type AuthMode = 'login' | 'register' | 'verify';
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function AuthPage() {
  const {
    loading,
    error,
    pendingEmail,
    needsOtpVerification,
    signInWithEmail,
    signUpWithEmail,
    verifyOtp,
    resendOtp,
    continueAsGuest,
    clearError,
    clearPendingVerification,
  } = useAuthStore();

  const [mode, setMode] = useState<AuthMode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [emailTouched, setEmailTouched] = useState(false);
  const [localMessage, setLocalMessage] = useState('');
  const [localError, setLocalError] = useState('');

  useEffect(() => {
    if (needsOtpVerification && pendingEmail) {
      setMode('verify');
      setEmail(pendingEmail);
      setLocalMessage(`We sent a verification email or code to ${pendingEmail}.`);
    }
  }, [needsOtpVerification, pendingEmail]);

  const normalizedEmail = useMemo(() => email.trim(), [email]);
  const isEmailValid = normalizedEmail.length > 0 && EMAIL_REGEX.test(normalizedEmail);
  const showEmailError = emailTouched && normalizedEmail.length > 0 && !isEmailValid;
  const displayError = localError || error || '';

  const resetMessages = () => {
    clearError();
    setLocalError('');
    setLocalMessage('');
  };

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    resetMessages();
    setEmailTouched(true);
    if (!normalizedEmail || !password) {
      setLocalError('Enter your email and password.');
      return;
    }
    if (!isEmailValid) {
      setLocalError('Enter a valid email address.');
      return;
    }
    await signInWithEmail(normalizedEmail, password);
  };

  const handleRegister = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    resetMessages();
    setEmailTouched(true);
    if (!normalizedEmail || !password || !confirmPassword) {
      setLocalError('Complete all registration fields.');
      return;
    }
    if (!isEmailValid) {
      setLocalError('Enter a valid email address.');
      return;
    }
    if (password !== confirmPassword) {
      setLocalError('Passwords do not match.');
      return;
    }
    if (password.length < 6) {
      setLocalError('Password must be at least 6 characters.');
      return;
    }

    const result = await signUpWithEmail(normalizedEmail, password);
    if (!result.needsVerification) {
      setLocalMessage('Account created and signed in.');
    }
  };

  const handleVerify = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    resetMessages();
    const emailToVerify = pendingEmail || normalizedEmail;
    if (!emailToVerify || !otpCode.trim()) {
      setLocalError('Enter the verification code.');
      return;
    }
    await verifyOtp(emailToVerify, otpCode);
  };

  const handleResend = async () => {
    resetMessages();
    const emailToVerify = pendingEmail || normalizedEmail;
    if (!emailToVerify) {
      setLocalError('Missing pending email.');
      return;
    }
    await resendOtp(emailToVerify);
    setLocalMessage(`Resent to ${emailToVerify}.`);
  };

  const switchMode = (nextMode: Exclude<AuthMode, 'verify'>) => {
    resetMessages();
    if (mode === 'verify') {
      clearPendingVerification();
      setOtpCode('');
    }
    setMode(nextMode);
  };

  return (
    <div className="min-h-screen bg-[var(--surface)] px-4 py-10 transition-colors duration-500 relative overflow-hidden">
      {/* Theme Toggle for Auth Page */}
      <div className="absolute top-6 right-6 z-20">
        <ThemeToggle />
      </div>

      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-md items-center relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="w-full rounded-[32px] border border-[var(--border)] bg-[var(--surface-low)] p-10 shadow-2xl backdrop-blur-md"
        >
          <div className="mb-10 text-center">
            <div className="w-16 h-16 bg-gradient-to-br from-[var(--accent)] to-blue-600 rounded-2xl mx-auto mb-6 flex items-center justify-center shadow-lg transform -rotate-6">
              <Lock size={32} className="text-white" />
            </div>
            <h1 className="text-4xl font-black text-[var(--text-primary)] tracking-tight font-display mb-2">LawNidhi</h1>
            <p className="text-sm text-[var(--text-secondary)] font-medium">
              {mode === 'register' ? 'Create legal workspace' : mode === 'verify' ? 'Secure your account' : 'Enterprise Access'}
            </p>
          </div>

          {mode !== 'verify' && (
            <div className="mb-8 flex rounded-2xl bg-[var(--surface-high)] p-1.5 border border-[var(--border)]">
              <button
                type="button"
                onClick={() => switchMode('login')}
                className={`flex-1 rounded-xl px-4 py-3 text-sm font-bold transition-all ${
                  mode === 'login' ? 'bg-[var(--surface-low)] text-[var(--text-primary)] shadow-md border border-[var(--border)]' : 'text-[var(--text-secondary)]'
                }`}
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => switchMode('register')}
                className={`flex-1 rounded-xl px-4 py-3 text-sm font-bold transition-all ${
                  mode === 'register' ? 'bg-[var(--surface-low)] text-[var(--text-primary)] shadow-md border border-[var(--border)]' : 'text-[var(--text-secondary)]'
                }`}
              >
                Register
              </button>
            </div>
          )}

          {mode === 'login' && (
            <form onSubmit={handleLogin} className="space-y-4">
              <label className="block">
                <span className="mb-2 block text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest px-1">Email Address</span>
                <div className="flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-high)] px-4 py-4 focus-within:ring-2 focus-within:ring-[var(--accent)]/30 transition-all">
                  <Mail size={18} className="text-[var(--text-muted)]" />
                  <input
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      if (localError) setLocalError('');
                    }}
                    onBlur={() => setEmailTouched(true)}
                    placeholder="counsel@legal.corp"
                    inputMode="email"
                    required
                    className="w-full border-0 bg-transparent text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
                  />
                </div>
              </label>
              {showEmailError && <p className="text-sm text-rose-600">Enter a valid email address.</p>}

              <label className="block">
                <span className="mb-2 block text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest px-1">Security Key</span>
                <div className="flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-high)] px-4 py-4 focus-within:ring-2 focus-within:ring-[var(--accent)]/30 transition-all">
                  <Lock size={18} className="text-[var(--text-muted)]" />
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full border-0 bg-transparent text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
                  />
                </div>
              </label>

              <button
                type="submit"
                disabled={loading}
                className="inline-flex w-full items-center justify-center gap-3 rounded-2xl bg-[var(--accent)] px-5 py-4 text-sm font-bold text-white transition-all hover:bg-[var(--accent-dark)] shadow-xl shadow-[var(--accent)]/20 disabled:cursor-not-allowed disabled:opacity-60 mt-4"
              >
                {loading ? <Loader2 size={18} className="animate-spin" /> : <ArrowRight size={18} />}
                {loading ? 'Authenticating...' : 'Enter Workspace'}
              </button>
            </form>
          )}

          {mode === 'register' && (
            <form onSubmit={handleRegister} className="space-y-4">
              <label className="block">
                <span className="mb-2 block text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest px-1">Email Address</span>
                <div className="flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-high)] px-4 py-4 focus-within:ring-2 focus-within:ring-[var(--accent)]/30 transition-all">
                  <Mail size={18} className="text-[var(--text-muted)]" />
                  <input
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      if (localError) setLocalError('');
                    }}
                    onBlur={() => setEmailTouched(true)}
                    placeholder="counsel@legal.corp"
                    inputMode="email"
                    required
                    className="w-full border-0 bg-transparent text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
                  />
                </div>
              </label>
              {showEmailError && <p className="text-sm text-rose-600">Enter a valid email address.</p>}

              <label className="block">
                <span className="mb-2 block text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest px-1">Security Key</span>
                <div className="flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-high)] px-4 py-4 focus-within:ring-2 focus-within:ring-[var(--accent)]/30 transition-all">
                  <Lock size={18} className="text-[var(--text-muted)]" />
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="At least 6 characters"
                    className="w-full border-0 bg-transparent text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
                  />
                </div>
              </label>

              <label className="block">
                <span className="mb-2 block text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest px-1">Confirm Identity</span>
                <div className="flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-high)] px-4 py-4 focus-within:ring-2 focus-within:ring-[var(--accent)]/30 transition-all">
                  <Lock size={18} className="text-[var(--text-muted)]" />
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Verify security key"
                    className="w-full border-0 bg-transparent text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
                  />
                </div>
              </label>

              <button
                type="submit"
                disabled={loading}
                className="inline-flex w-full items-center justify-center gap-3 rounded-2xl bg-[var(--accent)] px-5 py-4 text-sm font-bold text-white transition-all hover:bg-[var(--accent-dark)] shadow-xl shadow-[var(--accent)]/20 disabled:cursor-not-allowed disabled:opacity-60 mt-4"
              >
                {loading ? <Loader2 size={18} className="animate-spin" /> : <ArrowRight size={18} />}
                {loading ? 'Registering...' : 'Complete Registration'}
              </button>
            </form>
          )}

          {mode === 'verify' && (
            <form onSubmit={handleVerify} className="space-y-4">
              <div className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-700">
                Finish email verification to continue.
              </div>

              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate-700">Code</span>
                <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3">
                  <Mail size={18} className="text-slate-400" />
                  <input
                    type="text"
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value)}
                    placeholder="Enter the code"
                    className="w-full border-0 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
                  />
                </div>
              </label>

              <button
                type="submit"
                disabled={loading}
                className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
                {loading ? 'Verifying...' : 'Verify'}
              </button>

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => void handleResend()}
                  className="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  Resend
                </button>
                <button
                  type="button"
                  onClick={() => switchMode('login')}
                  className="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  Back
                </button>
              </div>
            </form>
          )}

          {localMessage && (
            <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {localMessage}
            </div>
          )}

          {displayError && (
            <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {displayError}
            </div>
          )}

          {mode !== 'verify' && (
            <div className="mt-8 text-center">
              <button
                type="button"
                onClick={continueAsGuest}
                className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest hover:text-[var(--accent)] transition-colors underline underline-offset-4"
              >
                Continue as Trial Witness
              </button>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
