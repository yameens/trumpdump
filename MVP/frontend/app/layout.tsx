import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'TrumpDump - White House Market Analysis',
  description: 'Real-time market impact analysis of White House announcements',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

