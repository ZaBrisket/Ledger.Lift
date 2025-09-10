import React from 'react';
import './globals.css';
import Providers from '../src/lib/Providers';

export const metadata = {
  title: 'Ledger Lift',
  description: 'Upload PDFs → data extraction',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
