import type { Metadata } from "next";
import "./globals.css";
import Nav from "./nav";

export const metadata: Metadata = {
  title: "Datenbrowser — S&P-500-Nachhaltigkeit",
  description:
    "Alle gesammelten Kennzahlen mit Quellenangabe an jedem einzelnen Wert.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap"
        />
      </head>
      <body>
        <Nav />
        <div className="shell">{children}</div>
      </body>
    </html>
  );
}
