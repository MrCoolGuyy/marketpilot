# MarketPilot

MarketPilot adalah sistem simulasi dan analisis kripto yang dirancang khusus untuk memonitor, menganalisis, dan mensimulasikan strategi pada pasar linear berkuotasi USDT di Bybit.

> **PENTING:** MarketPilot adalah perangkat lunak simulasi dan analisis **lokal**. Fokus aplikasi saat ini *hanya* pada analisis derivatif linear USDT. **Belum ada** fitur auto buy/sell menggunakan dana riil.

## Fitur Utama

- **Analisis Pasar & Scanner**: Memindai pasangan USDT secara *real-time* untuk mencari peluang *breakout* dengan filter volume.
- **Indikator & Strategi**: Pipeline indikator teknikal (EMA, RSI, ATR) dan evaluasi sinyal secara sinkron.
- **Manajemen Risiko**: Penyesuaian ukuran posisi teoritis menggunakan ATR dan kontrol penarikan maksimum (*max drawdown*).
- **Paper Trading Lokal**: Simulasi *trading* secara *real-time* menggunakan buku besar (ledger) SQLite lokal. Sama sekali tidak menyentuh saldo Bybit Anda.
- **Position Manager**: Menilai posisi paper secara lokal terhadap harga pasar, memungkinkan penutupan posisi via CLI.
- **Backtesting & Optimasi**: Engine simulasi murni *in-memory* yang memutar ulang data harga historis (tidak menjamin profitabilitas masa depan).
- **Demo Trading Execution**: Eksekusi posisi *real-time* ke Bybit Demo Trading secara aman. **Dilengkapi pengamanan ketat** untuk memblokir eksekusi di Mainnet/Testnet campuran.
- **Candidate Autopilot**: Menyeleksi kandidat *trading* terbaik (berdasarkan sinyal, RSI, dan pergerakan tren) untuk dieksekusi secara otomatis ke Demo Trading jika syarat manajemen risiko terpenuhi.
- **Dashboard Control Center**: Dasbor web lokal interaktif (127.0.0.1) untuk pemantauan portofolio dan pasar dengan kapabilitas kontrol manual (wajib menggunakan Control Key rahasia).
- **Notifikasi Telegram**: Notifikasi satu arah (outbound-only) ke Telegram untuk memberi tahu tentang sinyal atau penutupan posisi paper/demo.

## Quick Start

### 1. Instalasi

Pastikan Anda menggunakan Python versi terbaru dan `uv` untuk manajemen package. Instal semua dependency:

```bash
uv sync
```

### 2. Konfigurasi Kredensial (Sangat Penting)

Salin `.env.example` ke `.env` lalu isi konfigurasi Anda. 

```bash
cp .env.example .env
```
**Peringatan Keamanan Kredensial:** Kredensial API dan token Telegram **hanya boleh** diletakkan di dalam file `.env`. Jangan pernah memasukkannya ke dalam dokumentasi, git, log sistem, atau chat. Bila token Telegram Anda tidak sengaja terekspos, Anda **wajib** melakukan *rotate* token melalui BotFather.

### 3. Migrasi Database

Sebelum menggunakan manajemen posisi, pastikan skema database lokal Anda mutakhir:

```bash
uv run marketpilot migrate --confirm
```

### 4. Konfigurasi Autopilot & Demo (Opsional)

Untuk menjalankan Autopilot atau eksekusi Demo, Anda membutuhkan `DEMO_API_KEY` dan `DEMO_API_SECRET` dari Bybit Demo Trading. Isikan di `.env` dan aktifkan mode Demo. Jangan gunakan API Key Mainnet!

Untuk menggunakan Control Center di Dashboard, Anda harus mengeset `DASHBOARD_CONTROL_KEY` di `.env`.

### 5. Mulai Eksplorasi

Periksa konektivitas ke API publik Bybit:
```bash
uv run marketpilot ping
```

Tampilkan dashboard web di browser Anda:
```bash
uv run marketpilot dashboard
```

Untuk detail perintah selengkapnya dan cara penggunaan harian, silakan baca [Manual Penggunaan Lengkap](docs/MANUAL_PENGGUNAAN.md).
