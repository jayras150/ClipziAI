// Deklarasi wildcard untuk file aset non-TS.
//
// PENTING: file ini HARUS script-mode (tanpa `import`/`export`). Bila ada
// `export {}`, TypeScript memperlakukan file ini sebagai MODULE sehingga
// `declare module "*.css"` tidak dibuat sebagai wildcard global dan
// `import "./globals.css"` akan error TS2307/TS2882.

declare module "*.css";
declare module "*.scss";
declare module "*.sass";

declare module "*.svg" {
  const content: string;
  export default content;
}

declare module "*.png" {
  const content: string;
  export default content;
}

declare module "*.jpg" {
  const content: string;
  export default content;
}
