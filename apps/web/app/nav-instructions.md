To surface the new Convert page in your global nav, import and render `NavAppendix` in `app/layout.tsx` near your existing navigation.

Example:
```tsx
import NavAppendix from '../src/components/NavAppendix';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Header />
        <NavAppendix />
        {children}
      </body>
    </html>
  );
}
```
