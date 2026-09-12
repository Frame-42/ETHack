"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Firmen" },
  { href: "/vergleich", label: "Vergleich" },
  { href: "/kennzahlen", label: "Kennzahlen" },
  { href: "/quellen", label: "Quellen" },
  { href: "/downloads", label: "Downloads" },
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
        <a
          className="stamp"
          href="/datenkatalog.pdf"
          download="ETHack-Datenkatalog.pdf"
        >
          Datenkatalog als PDF ↓
        </a>
      </div>
    </header>
  );
}
