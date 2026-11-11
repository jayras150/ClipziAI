---
name: rules
description: Brief description of what this skill does
---

---
name: rules
description: Global development rules for AI coding agents. Enforces Indonesian communication, production-grade implementation, efficient execution, mandatory TODO.md review, comprehensive testing, README documentation, and strict Git commit requirements.
---

**# rules**

Instructions for the AI agent. These rules must be followed throughout the entire development process.

**## Usage**

Apply this skill to every software development task, including:

- Creating new applications and features.
- Modifying existing code.
- Debugging and fixing errors.
- Refactoring and optimizing code.
- Installing or configuring dependencies.
- Updating project architecture.
- Building, testing, and deploying applications.
- Maintaining existing projects.

These rules are mandatory. Do not skip steps simply because a task appears simple.

**## Core Rules**

1. **Bahasa Indonesia**
   - Selalu gunakan Bahasa Indonesia untuk menjelaskan proses, analisis, hasil, dan instruksi kepada pengguna.
   - Pertahankan bahasa asli pada kode, nama variabel, API, dan dokumentasi teknis jika diperlukan.
   - Jangan mengubah bahasa komunikasi tanpa instruksi pengguna.

2. **Production-Grade Code**
   - Semua implementasi wajib production-grade.
   - Dilarang membuat dummy implementation, placeholder, mock implementation untuk menggantikan fitur sebenarnya, atau kode sekadar demonstrasi.
   - Jangan meninggalkan fungsi kosong, implementasi setengah jadi, atau fitur yang hanya terlihat berfungsi.
   - Gunakan error handling, validasi input, logging, security, dan type safety sesuai kebutuhan proyek.
   - Ikuti arsitektur, coding convention, dan standar teknologi yang sudah digunakan proyek.

3. **Execution Efficiency**
   - Jalankan perintah secepat mungkin tanpa mengorbankan keamanan dan akurasi.
   - Hindari proses yang tidak diperlukan, pengulangan command, dan pemeriksaan berlebihan.
   - Jangan membuat pengguna menunggu lama jika pekerjaan dapat dilakukan secara paralel atau lebih efisien.
   - Berikan informasi jika suatu proses memang membutuhkan waktu lama.

4. **Code Quality**
   - Pahami kode yang sudah ada sebelum melakukan perubahan.
   - Hindari duplikasi kode dan implementasi yang tidak diperlukan.
   - Jangan menghapus fitur yang sudah berjalan tanpa alasan teknis yang jelas.
   - Pertahankan kompatibilitas dengan komponen lain.
   - Jangan mengubah konfigurasi atau dependency tanpa memahami dampaknya.

**## Steps**

**1. Inspect Project**

- Periksa struktur direktori dan arsitektur proyek.
- Identifikasi bahasa pemrograman, framework, dependency, dan konfigurasi yang digunakan.
- Periksa `README.md` untuk memahami dokumentasi proyek.
- **WAJIB membaca `TODO.md` sebelum memulai pekerjaan.**
- Identifikasi tugas yang berkaitan dengan permintaan pengguna.
- Jika terdapat tugas terkait yang dapat dikerjakan bersama tanpa memperluas scope secara tidak wajar, kerjakan sekaligus.
- Periksa implementasi yang sudah tersedia sebelum membuat kode baru.

**2. Analyze Requirements**

- Pahami kebutuhan pengguna secara menyeluruh.
- Identifikasi file yang perlu dibuat, dimodifikasi, atau dihapus.
- Analisis dependency dan dampak perubahan terhadap komponen lain.
- Identifikasi potensi bug, security issues, dan risiko kompatibilitas.
- Tentukan pendekatan implementasi paling efektif.
- Jangan menebak detail teknis yang dapat diperiksa langsung dari source code.

**3. Implementation**

- Implementasikan seluruh fitur sesuai kebutuhan.
- Gunakan implementasi nyata dan production-grade.
- Ikuti struktur dan standar proyek.
- Jangan mengganti sistem yang sudah berjalan tanpa alasan yang kuat.
- Jangan menghapus kode atau fitur yang masih digunakan.
- Pastikan seluruh integrasi berjalan dengan benar.
- Tangani edge cases dan kemungkinan kegagalan.
- Jangan menyatakan fitur selesai jika implementasinya belum lengkap.

**4. Pre-Build Validation**

Sebelum menjalankan build:

- Periksa seluruh perubahan kode.
- Periksa syntax dan type errors.
- Periksa import dan dependency.
- Periksa konfigurasi.
- Periksa kemungkinan circular dependency.
- Periksa keamanan dan validasi input.
- Periksa kompatibilitas antar-komponen.
- Jalankan formatter dan linter jika tersedia.
- Perbaiki kesalahan yang ditemukan sebelum melanjutkan.

**5. Build and Testing**

- Jalankan build menggunakan command resmi proyek.
- Jalankan unit tests, integration tests, dan relevant automated tests.
- Jalankan pemeriksaan tambahan sesuai teknologi yang digunakan.
- Perbaiki seluruh error yang ditemukan.
- Ulangi build dan testing setelah melakukan perbaikan.
- Jangan menganggap build berhasil hanya karena command tidak menampilkan error secara langsung.
- Pastikan exit code dan hasil proses menunjukkan keberhasilan.
- Jangan mengklaim pengujian berhasil jika belum benar-benar dijalankan.

**6. VS Code Problems Verification**

- Periksa panel `@problems` di VS Code.
- Pastikan tidak ada error yang belum terselesaikan.
- Periksa warning yang berkaitan dengan perubahan.
- Jangan menyembunyikan error dengan menonaktifkan diagnostic rules, linter, atau type checking.
- Jika akses ke panel VS Code tidak tersedia, gunakan pemeriksaan alternatif dan jelaskan keterbatasannya.
- Jangan mengklaim `@problems` memiliki 0 Errors jika belum diverifikasi.

**7. README.md Documentation**

Setiap perubahan fitur, konfigurasi, dependency, atau arsitektur wajib didokumentasikan di `README.md` jika relevan.

Dokumentasi minimal harus menjelaskan:

- Fungsi dan tujuan fitur.
- Cara instalasi dan penggunaan.
- Cara konfigurasi.
- Lokasi file konfigurasi.
- Cara mengganti atau memperbarui konfigurasi.
- Cara mengganti provider, API, model, database, atau storage jika relevan.
- Cara melakukan modifikasi dan maintenance.
- Command untuk build, testing, dan deployment.
- Troubleshooting untuk masalah umum.

Ketentuan:

- Dokumentasi harus akurat dan sesuai implementasi sebenarnya.
- Jangan mendokumentasikan fitur yang belum diimplementasikan seolah-olah sudah tersedia.
- Jangan menuliskan API key, password, token, atau secret ke dalam dokumentasi.
- Gunakan contoh konfigurasi yang aman.

**8. TODO.md Management**

- Periksa `TODO.md` sebelum memulai pekerjaan.
- Identifikasi semua tugas yang berkaitan dengan pekerjaan saat ini.
- Kerjakan tugas terkait yang masih berada dalam scope.
- Perbarui status checklist hanya setelah tugas benar-benar selesai.
- Gunakan `[x]` hanya jika implementasi sudah selesai dan diverifikasi.
- Gunakan `[ ]` untuk tugas yang belum selesai.
- Jangan menandai pekerjaan selesai hanya karena kode sudah ditulis.
- Pastikan status `TODO.md` sesuai kondisi proyek sebenarnya.

**9. Git Commit and Push Protection**

Dilarang melakukan commit atau push ke GitHub sebelum seluruh implementasi selesai dan diverifikasi.

Sebelum commit atau push, pastikan:

- Semua pekerjaan dalam scope sudah selesai.
- Tidak ada implementasi setengah jadi.
- Build berhasil.
- Testing yang relevan berhasil.
- VS Code `@problems` menunjukkan 0 Errors.
- Tidak ada perubahan yang tidak disengaja.
- `README.md` sudah diperbarui.
- `TODO.md` sudah diperbarui.
- `git diff` dan `git status` sudah diperiksa.
- Tidak ada secret, API key, password, atau credential yang ikut ter-commit.

Jangan melakukan commit atau push tanpa permintaan atau izin pengguna.

**10. Final Verification**

Sebelum menyatakan pekerjaan selesai:

- Review seluruh perubahan.
- Pastikan implementasi sesuai kebutuhan pengguna.
- Pastikan fitur berjalan sebagaimana mestinya.
- Pastikan build dan testing berhasil.
- Pastikan dokumentasi diperbarui.
- Pastikan `TODO.md` mencerminkan kondisi sebenarnya.
- Laporkan error atau keterbatasan yang belum terselesaikan secara transparan.

**## Command Execution Rules**

- Utamakan command yang cepat dan langsung.
- Hindari menjalankan command yang sama berulang kali tanpa alasan.
- Gunakan paralelisasi jika beberapa proses tidak saling bergantung.
- Jangan menjalankan proses berat jika pemeriksaan sederhana sudah cukup.
- Jangan menghentikan proses penting sebelum selesai.
- Jangan menghapus file, direktori, database, atau konfigurasi penting tanpa memastikan dampaknya.
- Minta konfirmasi sebelum melakukan tindakan destruktif atau tindakan yang sulit dibatalkan.

**## Error Handling Rules**

Jika menemukan error:

1. Identifikasi sumber error berdasarkan log dan source code.
2. Tentukan penyebab sebenarnya, bukan sekadar menghilangkan pesan error.
3. Perbaiki akar masalah.
4. Periksa dampak perbaikan terhadap komponen lain.
5. Jalankan kembali pemeriksaan dan testing yang relevan.
6. Dokumentasikan jika perubahan memengaruhi penggunaan atau konfigurasi.

Dilarang:

- Mengabaikan error.
- Menutupi error menggunakan workaround yang tidak tepat.
- Menghapus validasi untuk membuat build berhasil.
- Mengubah konfigurasi compiler atau linter hanya agar error menghilang.
- Mengklaim masalah selesai tanpa verifikasi.

**## Completion Report**

Setiap pekerjaan harus diakhiri dengan laporan singkat berisi:

1. **Implementasi:** fitur atau perubahan yang berhasil dibuat.
2. **File Changes:** file yang dibuat, dimodifikasi, atau dihapus.
3. **Testing:** pemeriksaan dan pengujian yang sudah dijalankan beserta hasilnya.
4. **Documentation:** perubahan dokumentasi `README.md`.
5. **TODO:** status tugas yang diselesaikan.
6. **Issues:** error atau keterbatasan yang masih tersisa.
7. **Git Status:** status commit atau push jika relevan.

Jangan pernah menyatakan pekerjaan 100% selesai jika masih ada bagian yang belum diimplementasikan atau belum diverifikasi.