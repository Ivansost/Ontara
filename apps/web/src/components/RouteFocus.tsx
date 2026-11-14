'use client';
import { useEffect } from 'react';
import { usePathname } from 'next/navigation';

export function RouteFocus() {
  const pathname = usePathname();
  useEffect(() => {
    const timeout = window.setTimeout(() => {
      const heading = document.querySelector<HTMLElement>('main h1');
      if (heading) {
        heading.setAttribute('tabindex', '-1');
        heading.focus({ preventScroll: true });
      }
    }, 80);
    return () => window.clearTimeout(timeout);
  }, [pathname]);
  return null;
}
