// Deklarasi tipe untuk side-effect import CSS global (mis. `import "./globals.css"`).
// Next.js/types hanya mendeklarasikan `*.module.css`, sehingga tanpa deklarasi ini
// TypeScript alias editor melaporkan error ts(2882).
declare module "*.css";
