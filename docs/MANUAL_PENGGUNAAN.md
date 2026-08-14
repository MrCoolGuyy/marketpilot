# Manual Penggunaan MarketPilot

Selamat datang di MarketPilot, alat analisis dan simulasi pasar kripto derivatif (USDT Linear) di Bybit berbasis command-line (CLI) dan dasbor web lokal. Panduan ini dirancang untuk operator (non-developer) agar dapat mengoperasikan sistem dengan aman.

## Batasan Sistem (Fase-4) Wajib Dibaca

- **Fokus Aplikasi**: Secara ketat hanya beroperasi pada pasar **USDT Linear** di Bybit (contoh: `BTCUSDT`, `ETHUSDT`). Tidak mendukung instrumen Spot.
- **Bukan Bot Trading Otomatis**: **Belum ada** fitur auto buy/sell yang menggunakan uang sungguhan (*Mainnet*). Semua eksekusi *live* ke uang sungguhan saat ini diblokir secara mutlak.
- **Dasbor Read-Only**: Dasbor web saat ini bersifat *read-only* (hanya dapat membaca/menampilkan data). Dasbor ini mengambil data pasar publik dan menampilkan hasil evaluasi dari `daemon`.
- **Keamanan Kredensial**: Semua token (Bybit API, Telegram Bot Token) hanya boleh berada di file `.env`. Jangan pernah membagikan `.env` ke publik! Jika token Telegram Anda bocor, segera lakukan *revoke* (cabut token) via BotFather di Telegram.

---

## Memahami Lingkungan (PAPER vs DEMO vs LIVE)

MarketPilot membedakan eksekusi ke dalam tiga tingkatan keamanan:
1. **PAPER (Paper Trading)**: Simulasi 100% lokal. Order, saldo, dan posisi hanya dicatat di dalam *database* SQLite di komputer Anda. Sama sekali tidak menyentuh server atau dompet Bybit Anda. Sangat aman untuk uji coba.
2. **DEMO (Demo Trading)**: Simulasi terhubung ke Bybit V5 Demo Trading. Order dikirim ke server demo Bybit. Membutuhkan API Key Demo khusus (bukan Mainnet).
3. **LIVE (Uang Riil)**: **(Belum Tersedia)**. Mengeksekusi order dengan uang sungguhan saat ini tidak diizinkan. Sistem akan menolak kredensial Mainnet jika fitur mutasi diaktifkan.

---

## Quick Start (Mulai Cepat) & Alur Kerja Harian

Untuk pengoperasian harian yang optimal, Anda disarankan menggunakan **2 jendela terminal (PowerShell / Command Prompt)**.

1. **Pastikan konfigurasi siap**: Anda harus sudah memiliki file `.env` yang berisi kredensial Bybit Anda.
2. **Verifikasi Koneksi API**: 
   Di terminal mana saja, ketik perintah berikut untuk memastikan Anda bisa terhubung ke server Bybit:
   ```bash
   uv run marketpilot ping
   ```
3. **Buka Terminal 1 (Dasbor UI)**:
   Jalankan server dasbor (UI) agar Anda bisa memantau pasar melalui browser.
   ```bash
   uv run marketpilot dashboard
   ```
   Buka browser Anda dan kunjungi: **`http://127.0.0.1:8000`**

4. **Buka Terminal 2 (Daemon Mesin Utama)**:
   Jalankan mesin utama yang bertugas mengevaluasi strategi. Evaluasi ini akan diproyeksikan dan otomatis muncul di Dasbor (Terminal 1).
   ```bash
   uv run marketpilot daemon
   ```
   *Catatan*: Jika Anda hanya ingin mengevaluasi satu siklus (sekali jalan lalu berhenti), gunakan perintah: `uv run marketpilot daemon --once`.

---

## Daftar Perintah CLI (Command Line) Lengkap

Seluruh perintah harus dijalankan menggunakan awalan `uv run marketpilot`. Sistem membagi perintah ke dalam dua kategori tingkat keamanan:

### Kategori [READ ONLY]
Perintah di bawah ini sangat aman. Mereka hanya *membaca* data atau melakukan simulasi *in-memory* tanpa mengubah database atau mengirim order apapun ke Bybit.

- **`ping`**
  Mengecek konektivitas dan waktu server (Server Time) ke API Publik Bybit.
  *Contoh:* `uv run marketpilot ping`

- **`scan`**
  Memindai seluruh aset USDT Linear di pasar untuk mencari koin dengan pergerakan volume tinggi.
  *Contoh:* `uv run marketpilot scan`

- **`indicators`**
  Menghitung dan menampilkan nilai indikator teknikal (seperti EMA, RSI, ATR) pada koin tertentu.
  *Contoh:* `uv run marketpilot indicators BTCUSDT 60` (Untuk koin BTCUSDT pada interval 60 menit)

- **`strategy`**
  Mengevaluasi logika algoritma *trading* (Sinyal LONG/SHORT/NEUTRAL) saat ini pada koin tertentu.
  *Contoh:* `uv run marketpilot strategy ETHUSDT 60`

- **`risk`**
  Mengecek batas risiko (*stop-loss*, *take-profit*) dan perhitungan ukuran posisi berdasarkan saldo Anda.
  *Contoh:* `uv run marketpilot risk BTCUSDT 60`

- **`backtest`**
  Mensimulasikan strategi pada data historis masa lalu di komputer secara lokal.
  *Contoh:* `uv run marketpilot backtest BTCUSDT 60 30` (Backtest 30 hari ke belakang)

- **`optimize`**
  Menjalankan tes berbagai parameter untuk mencari pengaturan indikator yang paling optimal pada koin tertentu.
  *Contoh:* `uv run marketpilot optimize BTCUSDT 60 30`

- **`dashboard`**
  Menjalankan server antarmuka web lokal (UI) yang bersifat *read-only*. Server berjalan di latar belakang dan dapat diakses via browser.
  *Contoh:* `uv run marketpilot dashboard`

- **`telegram`**
  Menguji notifikasi ke Telegram (memastikan bot dan Chat ID Anda terkonfigurasi dengan benar). Harus ditambah `--confirm`.
  *Contoh:* `uv run marketpilot telegram test --confirm`

- **`research`**
  Mengeksekusi skrip riset untuk mendiagnosa koin tertentu berdasarkan sinyal yang terjadi.
  *Contoh:* `uv run marketpilot research evaluate BTCUSDT`

### Kategori [MUTATION CAPABLE] (Perhatian!)
Perintah di bawah ini dapat **mengubah** data (mutasi database lokal) atau **mengirim eksekusi** (ke Paper/Demo). Gunakan dengan hati-hati.

- **`paper`**
  Mengeksekusi atau mereset posisi simulasi pada *database* lokal (Paper Trading).
  *Contoh:* `uv run marketpilot paper open BTCUSDT LONG`

- **`migrate`**
  Memperbarui kerangka *database* lokal (wajib dijalankan pertama kali atau setelah pembaruan aplikasi).
  *Contoh:* `uv run marketpilot migrate --confirm`

- **`positions`**
  Melihat dan memanajemen (menutup otomatis) posisi yang sedang berjalan jika sudah mencapai *stop-loss* atau target.
  *Contoh:* `uv run marketpilot positions check` (Hanya mengecek) atau `uv run marketpilot positions manage --confirm` (Akan menutup posisi jika kena batas)

- **`demo`**
  Mengeksekusi perintah langsung ke akun **Demo Trading Bybit**.
  *Contoh:* `uv run marketpilot demo open BTCUSDT LONG --confirm`

- **`daemon`**
  Menjalankan mesin utama MarketPilot secara utuh (*canonical Phase-3/4 daemon*). Daemon akan terus berjalan, mengambil harga, mengevaluasi strategi, dan memproyeksikan hasilnya.
  *Contoh:* `uv run marketpilot daemon` (Jalan terus) atau `uv run marketpilot daemon --once` (Jalan 1 siklus saja).

---

## Verifikasi Asap (Smoke Testing)

Jika Anda ingin memastikan sistem berfungsi penuh tanpa ada kode yang rusak, Anda dapat menjalankan verifikasi (uji coba internal otomatis) menggunakan Pytest:
```bash
uv run pytest
```
*Expected Output:* Semua pengujian (test) harus berjalan dengan sukses (100%). Peringatan *DeprecationWarning* yang berwarna kuning (seperti tentang `httpx` atau `starlette`) dapat diabaikan. Jika terjadi error yang berwarna merah (Failed), laporkan hal ini kepada tim teknis.

---

## Cara Mengatasi Masalah Umum (Troubleshooting)

### 1. `[WinError 10048] Only one usage of each socket address is normally permitted`
**Masalah**: Anda mencoba menjalankan `uv run marketpilot dashboard`, namun terminal menampilkan error tentang *port* 8000 atau alamat yang sudah terpakai.
**Penyebab**: Server dasbor di port 8000 masih berjalan di balik layar PowerShell Anda, atau ada dasbor lain yang belum ditutup sepenuhnya.
**Solusi**:
- Cek apakah Anda masih membuka tab terminal PowerShell lain yang menjalankan dasbor.
- Pada terminal yang menjalankan dasbor, tekan **`Ctrl + C`** beberapa kali untuk mematikannya secara paksa sebelum menjalankannya ulang.
- Jika masih error, Anda dapat menutup seluruh jendela terminal PowerShell Anda lalu membukanya kembali.

### 2. `ValidationError` atau Masalah Konfigurasi
**Penyebab**: Kemungkinan format konfigurasi di dalam file `.env` salah (misalnya, tertinggal tanda kutip atau kurang spasi).
**Solusi**: Buka file `.env` dan pastikan format pengisian kunci API sudah persis seperti contoh di `.env.example`.

### 3. Dasbor Web Kosong / Tidak Memuat Strategi
**Penyebab**: Dasbor saat ini dirancang hanya untuk membaca (read-only) hasil dari `daemon`. Jika `daemon` belum dijalankan, maka dasbor tidak memiliki data evaluasi.
**Solusi**: Buka terminal kedua, jalankan `uv run marketpilot daemon --once` dan tunggu siklus selesai. Layar Dasbor di browser akan otomatis memperbarui dirinya.
