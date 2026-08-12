import { useState, useEffect, useCallback } from 'react';
import { writeStorageValue } from '../services/safeStorage';

type Theme = 'light';

export function useTheme() {
  // The product visual language is intentionally blue-and-white.  Migrate any
  // older dark/system preference so an OS dark preference cannot turn the
  // workspace back into a black interface.
  const [theme, setThemeState] = useState<Theme>('light');

  const applyTheme = useCallback(() => {
    document.documentElement.setAttribute('data-theme', 'light');
  }, []);

  const setTheme = useCallback(() => {
    setThemeState('light');
    writeStorageValue('physics_vault_theme', 'light');
    applyTheme();
  }, [applyTheme]);

  useEffect(() => {
    applyTheme();
    writeStorageValue('physics_vault_theme', 'light');
  }, [theme, applyTheme]);

  return { theme, setTheme, isDark: false };
}
