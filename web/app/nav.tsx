"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Firmen" },
  { href: "/kennzahlen", label: "Kennzahlen" },
  { href: "/quellen", label: "Quellen" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <header className="top">
      <div className="top-inner">
        <Link href="/" className="brand">
          Datenbrowser <span>· S&amp;P-500-Nachhaltigkeit</span>
        </Link>
        <nav className="nav">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={path === l.href ? "on" : undefined}
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <span className="stamp">jeder Wert mit Quelle</span>
      </div>
    </header>
  );
}
