/** @type {import('next').NextConfig} */
export default {
  reactStrictMode: true,
  // Erzeugt einen eigenständigen Server unter .next/standalone -- nötig für
  // das schlanke Docker-Image.
  output: "standalone",
};
