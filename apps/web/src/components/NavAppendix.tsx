'use client';
import Link from 'next/link';

export default function NavAppendix() {
  return (
    <nav style={{ padding: '8px 0' }}>
      <Link href="/convert">PDF → Excel Schedules (Beta)</Link>
    </nav>
  );
}
