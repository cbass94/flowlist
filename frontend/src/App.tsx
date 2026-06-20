// FlowList — Root app component
// Auth-gates the main view; provides routing between Backlog, Archive, and Settings.

import { Routes, Route, NavLink, useLocation, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import { useTheme } from './hooks/useTheme';
import { LoginScreen } from './components/LoginScreen';
import { TaskInput } from './components/TaskInput';
import { BacklogView } from './components/BacklogView';
import { WatchdogWidget } from './components/WatchdogWidget';
import { SettingsPage } from './pages/SettingsPage';
import { ArchivePage } from './pages/ArchivePage';
import { InvitePage } from './pages/InvitePage';

// ---- Icons -------------------------------------------------------------------

function IconList() {
  return (
    <svg className='w-[18px] h-[18px]' fill='none' stroke='currentColor' strokeWidth={1.75} viewBox='0 0 24 24'>
      <path strokeLinecap='round' strokeLinejoin='round' d='M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' />
    </svg>
  );
}

function IconArchive() {
  return (
    <svg className='w-[18px] h-[18px]' fill='none' stroke='currentColor' strokeWidth={1.75} viewBox='0 0 24 24'>
      <path strokeLinecap='round' strokeLinejoin='round' d='M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4' />
    </svg>
  );
}

function IconSettings() {
  return (
    <svg className='w-[18px] h-[18px]' fill='none' stroke='currentColor' strokeWidth={1.75} viewBox='0 0 24 24'>
      <path strokeLinecap='round' strokeLinejoin='round' d='M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z' />
      <path strokeLinecap='round' strokeLinejoin='round' d='M15 12a3 3 0 11-6 0 3 3 0 016 0z' />
    </svg>
  );
}

function IconSun() {
  return (
    <svg className='w-4 h-4' fill='none' stroke='currentColor' strokeWidth={1.75} viewBox='0 0 24 24'>
      <circle cx='12' cy='12' r='5' strokeLinecap='round' strokeLinejoin='round' />
      <path strokeLinecap='round' strokeLinejoin='round' d='M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42' />
    </svg>
  );
}

function IconMoon() {
  return (
    <svg className='w-4 h-4' fill='none' stroke='currentColor' strokeWidth={1.75} viewBox='0 0 24 24'>
      <path strokeLinecap='round' strokeLinejoin='round' d='M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z' />
    </svg>
  );
}

// ---- Loading screen ----------------------------------------------------------

function LoadingScreen() {
  return (
    <div className='min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center'>
      <div className='flex items-center gap-2.5 text-gray-400 dark:text-gray-500 text-sm tracking-tight'>
        <svg className='w-4 h-4 animate-spin' viewBox='0 0 24 24' fill='none'>
          <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4' />
          <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v8H4z' />
        </svg>
        Loading...
      </div>
    </div>
  );
}

// ---- Page title helper -------------------------------------------------------

function usePageTitle() {
  const location = useLocation();
  if (location.pathname.startsWith('/archive')) return 'Archive';
  if (location.pathname.startsWith('/settings')) return 'Settings';
  return 'FlowList';
}

// ---- Desktop top nav ---------------------------------------------------------

function TopNav({ userName, theme, onToggleTheme }: {
  userName: string | null;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
}) {
  const title = usePageTitle();

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[13px] font-medium transition-all duration-150 ' +
    (isActive
      ? 'text-gray-900 dark:text-gray-50 bg-white dark:bg-gray-800 shadow-sm shadow-gray-200/60 dark:shadow-black/20 ring-1 ring-gray-950/[0.04] dark:ring-white/[0.04]'
      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-white/60 dark:hover:bg-gray-800/60');

  return (
    <header className='sticky top-0 z-20 bg-gray-50/80 dark:bg-gray-950/80 backdrop-blur-xl border-b border-gray-200/60 dark:border-gray-700/60'>
      <div className='max-w-2xl mx-auto px-4 h-14 flex items-center justify-between'>
        <div className='flex items-center gap-1.5'>
          <span className='font-semibold text-gray-900 dark:text-gray-50 text-base tracking-tight mr-3'>{title}</span>
          <nav className='hidden sm:flex items-center gap-0.5 bg-gray-100/80 dark:bg-gray-800/80 rounded-lg p-0.5'>
            <NavLink to='/' end className={navLinkClass}>
              <IconList />
              Backlog
            </NavLink>
            <NavLink to='/archive' className={navLinkClass}>
              <IconArchive />
              Archive
            </NavLink>
            <NavLink to='/settings' className={navLinkClass}>
              <IconSettings />
              Settings
            </NavLink>
          </nav>
        </div>
        <div className='flex items-center gap-3'>
          {userName && (
            <span className='text-xs text-gray-400 dark:text-gray-500 hidden sm:block truncate max-w-[160px]'>
              {userName}
            </span>
          )}
          <button
            onClick={onToggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            className='text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1 rounded-md'
          >
            {theme === 'dark' ? <IconSun /> : <IconMoon />}
          </button>
        </div>
      </div>
    </header>
  );
}

// ---- Mobile bottom tab bar ---------------------------------------------------

function BottomTabBar() {
  const tabClass = ({ isActive }: { isActive: boolean }) =>
    'flex flex-col items-center gap-0.5 py-2.5 px-5 flex-1 transition-colors duration-150 ' +
    (isActive ? 'text-gray-900 dark:text-gray-50' : 'text-gray-400 dark:text-gray-500');

  return (
    <nav className='fixed bottom-0 left-0 right-0 z-20 bg-white/80 dark:bg-gray-900/80 backdrop-blur-xl border-t border-gray-200/60 dark:border-gray-700/60 flex sm:hidden safe-area-bottom'>
      <NavLink to='/' end className={tabClass}>
        <IconList />
        <span className='text-[10px] font-medium'>Backlog</span>
      </NavLink>
      <NavLink to='/archive' className={tabClass}>
        <IconArchive />
        <span className='text-[10px] font-medium'>Archive</span>
      </NavLink>
      <NavLink to='/settings' className={tabClass}>
        <IconSettings />
        <span className='text-[10px] font-medium'>Settings</span>
      </NavLink>
    </nav>
  );
}

// ---- Backlog page ------------------------------------------------------------

function BacklogPage() {
  return (
    <div className='space-y-5'>
      <WatchdogWidget />
      <section>
        <TaskInput />
      </section>
      <section>
        <BacklogView />
      </section>
    </div>
  );
}

// ---- Authenticated shell -----------------------------------------------------

function AuthenticatedApp() {
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const userName = user?.display_name ?? user?.email ?? null;

  return (
    <div className='min-h-screen bg-gray-50 dark:bg-gray-950'>
      <TopNav userName={userName} theme={theme} onToggleTheme={toggleTheme} />
      <main className='max-w-2xl mx-auto px-4 py-6 pb-24'>
        <Routes>
          <Route path='/' element={<BacklogPage />} />
          <Route path='/archive' element={<ArchivePage />} />
          <Route path='/settings' element={<SettingsPage />} />
          <Route path='*' element={<Navigate to='/' replace />} />
        </Routes>
      </main>
      <BottomTabBar />
    </div>
  );
}

// ---- Root --------------------------------------------------------------------

export default function App() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (location.pathname.startsWith('/invite')) {
    return <InvitePage />;
  }

  if (isLoading) return <LoadingScreen />;
  if (!isAuthenticated) return <LoginScreen />;

  return <AuthenticatedApp />;
}
