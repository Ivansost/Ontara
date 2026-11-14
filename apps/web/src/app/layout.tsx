import type { Metadata, Viewport } from 'next';
import { AppFrame } from '@/components/AppFrame';
import './globals.css';

export const metadata: Metadata = {
  title: { default: 'Ontara — Report a local problem', template: '%s · Ontara' },
  description: 'Report a non-emergency local problem, review where it goes, and follow the next steps. A controlled municipal reporting demonstration.',
  robots: { index: false, follow: false },
};
export const viewport: Viewport = { width: 'device-width', initialScale: 1, viewportFit: 'cover' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AppFrame>{children}</AppFrame></body></html>;
}
