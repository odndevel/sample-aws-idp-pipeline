import { useAuth } from 'react-oidc-context';
import * as React from 'react';

import { useMemo } from 'react';

import Config from '../../config';
import { Link, useLocation } from '@tanstack/react-router';

/**
 * Defines the App layout and contains logic for routing.
 */
const AppLayout: React.FC<React.PropsWithChildren> = ({ children }) => {
  const { user, removeUser, signoutRedirect, clearStaleState } = useAuth();
  const { pathname } = useLocation();
  const navItems = useMemo(
    () => [
      { to: '/', label: 'Projects' },
      { to: '/test', label: 'Test' },
    ],
    [],
  );
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="brand">
            <a href="/">
              <img
                src={Config.logo}
                alt={`${Config.applicationName} logo`}
                className="brand-logo"
              />
              <span className="brand-name">{Config.applicationName}</span>
            </a>
          </div>

          <nav className="app-nav">
            {navItems.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={pathname === item.to ? 'active' : undefined}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="user-greeting">
            <span>Hi, {`${user?.profile?.['cognito:username']}`}</span>
            <button
              type="button"
              className="signout-link"
              onClick={() => {
                removeUser();
                signoutRedirect({
                  post_logout_redirect_uri: window.location.origin,
                  extraQueryParams: {
                    redirect_uri: window.location.origin,
                    response_type: 'code',
                  },
                });
                clearStaleState();
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="app-main">
        <section className="card">{children}</section>
      </main>
    </div>
  );
};

export default AppLayout;
