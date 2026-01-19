import { useAuth } from 'react-oidc-context';
import * as React from 'react';
import { useMemo, useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import Config from '../../config';
import { Link, useLocation } from '@tanstack/react-router';

const UI_LANGUAGES = [
  { code: 'ko', name: '한국어', flag: '🇰🇷' },
  { code: 'en', name: 'English', flag: '🇺🇸' },
  { code: 'ja', name: '日本語', flag: '🇯🇵' },
];

/**
 * Defines the App layout and contains logic for routing.
 */
const AppLayout: React.FC<React.PropsWithChildren> = ({ children }) => {
  const { user, removeUser, signoutRedirect, clearStaleState } = useAuth();
  const { pathname } = useLocation();
  const { t, i18n } = useTranslation();
  const [showLangDropdown, setShowLangDropdown] = useState(false);
  const langDropdownRef = useRef<HTMLDivElement>(null);

  const navItems = useMemo(
    () => [
      { to: '/', label: t('nav.projects') },
      { to: '/test', label: 'Test' },
    ],
    [t],
  );

  const currentLang = UI_LANGUAGES.find((l) => l.code === i18n.language) || UI_LANGUAGES[1];

  const handleLanguageChange = (langCode: string) => {
    i18n.changeLanguage(langCode);
    setShowLangDropdown(false);
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        langDropdownRef.current &&
        !langDropdownRef.current.contains(event.target as Node)
      ) {
        setShowLangDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
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
          {/* Language Selector */}
          <div className="language-selector" ref={langDropdownRef}>
            <button
              type="button"
              className="lang-button"
              onClick={() => setShowLangDropdown(!showLangDropdown)}
            >
              <span className="lang-flag">{currentLang.flag}</span>
              <span className="lang-name">{currentLang.name}</span>
              <svg
                className={`lang-chevron ${showLangDropdown ? 'open' : ''}`}
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>
            {showLangDropdown && (
              <div className="lang-dropdown">
                {UI_LANGUAGES.map((lang) => (
                  <button
                    key={lang.code}
                    type="button"
                    className={`lang-option ${i18n.language === lang.code ? 'active' : ''}`}
                    onClick={() => handleLanguageChange(lang.code)}
                  >
                    <span className="lang-flag">{lang.flag}</span>
                    <span className="lang-name">{lang.name}</span>
                    {i18n.language === lang.code && (
                      <svg
                        className="lang-check"
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <path d="M20 6L9 17l-5-5" />
                      </svg>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="user-greeting">
            <span>{t('nav.greeting', { name: user?.profile?.['cognito:username'] })}</span>
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
              {t('nav.logout')}
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
