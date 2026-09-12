# Report build and verification

- The German report is `nachhaltigkeit_greenwashing_report.tex`; its bibliography is embedded, so no BibTeX or Biber step is needed.
- The PDF build was verified with Tectonic 0.15.0: `tectonic --untrusted --outdir . nachhaltigkeit_greenwashing_report.tex`.
- Tectonic must be available separately; it was run from a temporary installation during report creation. Its first build downloads TeX packages and fonts and requires working HTTPS access. Do not disable certificate verification to bypass download failures.
- The source selects Unicode OpenType fonts for XeTeX/Tectonic and a separate pdfTeX font setup. Bare `pdftex` without LaTeX formats and packages is insufficient.
- After changes, inspect compiler warnings for missing glyphs, unresolved references and overfull boxes. Use `pdfinfo` to verify the PDF and `pdftoppm` to spot-check rendered pages.
