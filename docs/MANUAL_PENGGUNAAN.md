# Manual Penggunaan MarketPilot

Selamat datang di MarketPilot, alat analisis dan simulasi pasar kripto derivatif berbasis command-line (CLI) dan dasbor web lokal.

## Batasan Sistem (Wajib Dibaca)

- **Fokus Aplikasi**: MarketPilot secara ketat hanya beroperasi pada **pasar derivatif linear yang berkuotasi USDT** di Bybit (contoh: `BTCUSDT`, `ETHUSDT`). Aplikasi ini tidak mendukung instrumen spot atau mata uang kripto selain USDT pada saat ini.
- **Bukan Bot Trading Otomatis**: **Belum ada** fitur *auto buy* atau *auto sell* yang menggunakan dana sungguhan (real funds). Semua fitur *trading* murni adalah simulasi.
- **Paper Trading Lokal**: Seluruh eksekusi *paper trading* dicatat di buku besar (ledger) SQLite lokal di perangkat Anda. Sistem sama sekali tidak membuat pesanan (*order*), mengirim dana, atau membaca saldo dompet Bybit Anda.
- **Demo Trading Execution**: Dapat diaktifkan untuk mengirim *order* ke akun **Bybit Demo Trading**. Eksekusi ke akun Mainnet dilarang keras dan diblokir secara mutlak pada tingkat *client*.
- **Dashboard Control Center**: Dasbor web bersifat aman untuk pemantauan, namun dapat mengeksekusi kontrol (Autopilot, Open/Close Demo) jika diotorisasi dengan `DASHBOARD_CONTROL_KEY` yang cocok via *request header*. Hanya boleh diakses melalui `127.0.0.1`.
- **Notifikasi Telegram**: Telegram terintegrasi secara *outbound-only*. Ini berarti bot hanya bisa *mengirim* notifikasi ke Anda, dan **tidak bisa** menerima perintah (*remote control*).
- **Keamanan Kredensial**: Semua token (Bybit API, Telegram Bot Token, dll.) hanya boleh berada di file `.env`. Jangan pernah membagikan `.env` ke publik, menyalinnya ke log, git, atau chat. Jika token Telegram Anda bocor atau terlihat, Anda harus segera melakukan **rotate token** via BotFather.
- **Backtest/Optimasi Tidak Menjamin Profit**: Segala hasil positif dalam *backtest* maupun *optimasi* tidak merepresentasikan keuntungan di masa depan.

---

## Daftar Perintah CLI (Command Line)

Berikut adalah daftar perintah terminal yang tersedia secara aktif pada MarketPilot. Semua perintah dijalankan menggunakan prefix `uv run marketpilot`.

### 1. Konektivitas & Lingkungan

- **`ping`**
  Memeriksa konektivitas koneksi HTTP dan WebSocket ke API Publik Bybit.

- **`migrate --confirm`**
  Memigrasi (memperbarui) skema database lokal secara aman. Wajib dijalankan agar `Position Manager` dapat bekerja, dan selalu membutuhkan flag `--confirm`.

- **`telegram test --confirm`**
  Mengirimkan notifikasi percobaan (ping) ke chat ID Telegram Anda untuk memastikan pengaturan `.env` sudah benar.

### 2. Analisis & Pemindaian Pasar

- **`scan`**
  Memindai seluruh aset linear USDT untuk mendeteksi pergerakan harga 24 jam dan memfilter aset berdasarkan volume harian tertinggi. 

- **`indicators <symbol> <interval>`**
  Menghitung dan mencetak nilai indikator teknikal (seperti EMA, RSI, ATR) pada koin tertentu (contoh: `BTCUSDT 60`).

- **`strategy <symbol> <interval>`**
  Mengevaluasi logika algoritma *trading* pada data historis secara *live* untuk mencari tahu arah sinyal (LONG/SHORT/NEUTRAL) terkini.

- **`risk <symbol> <interval>`**
  Menghitung ukuran posisi (position sizing) berdasarkan modal simulasi Anda, menghitung batas *stop-loss* serta *take-profit* menggunakan indikator volatilitas (ATR).

### 3. Simulasi Paper Trading & Manajemen Posisi

Paper trading adalah lingkungan yang terisolasi dari uang riil.

- **`paper reset --confirm`**
  Menghapus seluruh posisi, riwayat perdagangan, dan mengembalikan saldo simulasi kembali ke nominal awal secara permanen.

- **`paper status`**
  Menampilkan ringkasan saldo kas saat ini, margin terkunci, dan *unrealized PnL*.

- **`paper open <symbol> <direction>`**
  Membuka posisi simulasi pada pasar (contoh: `paper open BTCUSDT LONG`). Harga *entry* didasarkan pada harga pasar aktual saat perintah dieksekusi. 

- **`paper close <symbol>`**
  Menutup posisi simulasi secara paksa menggunakan harga pasar aktual saat ini.

- **`positions check`**
  Position Manager akan memindai seluruh posisi *paper* Anda yang sedang terbuka. Ia akan mengevaluasi batas *stop-loss* dan *take-profit* posisi tersebut melawan harga pasar publik Bybit lalu memberikan rekomendasi secara aman (*read-only*).

- **`positions manage --confirm`**
  Sama seperti perintah `check`, namun secara otomatis mengeksekusi penutupan posisi *paper* jika ada posisi yang menyentuh batas risiko (Hit Stop/Hit Target). Perintah ini memutasi database lokal.

### 4. Eksekusi Bybit Demo Trading & Autopilot

MarketPilot mendukung integrasi langsung dengan Bybit Demo Trading (harus diatur dalam `.env`). Dilarang keras menggunakan API Key Mainnet.

- **`demo open <symbol> --confirm`**
  Membuka posisi pada Bybit Demo Trading. Menggunakan penilaian risiko langsung dan harga pasar.
  
- **`demo close <symbol> --confirm`**
  Menutup posisi Bybit Demo Trading.
  
- **`demo autopilot run`**
  Menjalankan satu siklus Candidate Autopilot: menyeleksi peluang *breakout* terbaik, menilainya, dan (jika mode Auto Submit diaktifkan) secara otomatis membuka posisi Demo.

### 5. Simulasi Historis (In-Memory) & Riset

- **`backtest <symbol> <interval> <days>`**
  Mensimulasikan strategi pada periode waktu masa lalu secara sinkron.

- **`optimize <symbol> <interval> <days>`**
  Memutar berbagai kombinasi parameter indikator untuk mencari titik profitabilitas tertinggi pada set data historis yang ditentukan.

- **`research capture <symbol>`**
  Merekam parameter indikator dan risiko (snapshot harian lokal) tanpa melakukan pembukaan posisi, berguna untuk evaluasi di masa depan.
  
- **`research evaluate <symbol>`**
  Mengevaluasi hasil snapshot `capture` sebelumnya terhadap harga pasar publik yang datang setelah sinyal direkam, untuk mengukur efektivitas tanpa bias (*look-ahead bias*).

### 6. Dasbor Pemantauan

- **`dashboard`**
  Menjalankan server web Uvicorn lokal. Buka dasbor di `http://127.0.0.1:8000`. Memuat Autopilot Control Center untuk pemantauan dan kontrol secara *live*.

---

## Rutinitas Riset Harian

Agar simulasi lebih efektif dan realistis, sangat dianjurkan untuk mengikuti alur kerja berikut setiap harinya:

1. **Scan Pasar (`uv run marketpilot scan`)**  
   Cari kandidat koin dengan volume tertinggi dan perubahan volatilitas yang menarik.

2. **Analisis Pair Kandidat (`uv run marketpilot strategy ...`)**  
   Pilih satu atau dua koin hasil *scan*, kemudian jalankan analisis indikator, evaluasi strategi, dan *risk assessment* pada *timeframe* yang Anda inginkan.

3. **Backtest dan Optimasi (`uv run marketpilot backtest ...` & `optimize ...`)**  
   Uji koin tersebut secara historis. Jika hasilnya buruk, coba koin lain atau optimasi parameternya. (*Ingat: tidak ada garansi profit!*)

4. **Catat Keputusan Paper Trading (`uv run marketpilot paper open ...`)**  
   Bila strategi dan manajemen risiko setuju, buka posisi pada buku besar *paper trading* lokal Anda.

5. **Cek Paper Status & Positions Check**  
   Secara berkala, jalankan `paper status` dan `positions check` untuk melihat kinerja seluruh posisi terbuka Anda melawan kondisi *live market*. Apabila diperlukan, jalankan `positions manage --confirm`.

6. **Tinjau Dashboard (`uv run marketpilot dashboard`)**  
   Biarkan *dashboard* menyala di layar lain untuk memantau indikator terkini dan status evaluasi portofolio *paper trading* Anda secara terus-menerus tanpa harus sering mengetik perintah CLI.

---

## Troubleshooting (Penyelesaian Masalah)

Jika Anda menemui kendala, periksa hal-hal berikut:

- **Konfigurasi `.env` Bermasalah / Tidak Terbaca**  
  Pastikan nama file **persis** `.env` (tanpa ekstensi .txt). Pastikan variabel `BYBIT_API_KEY`, `BYBIT_API_SECRET`, dan `DB_URL` sudah benar formatnya.

- **Dashboard / Report Kosong (404)**  
  Dasbor memuat hasil berdasarkan eksekusi CLI terakhir. Jika Anda melihat pesan *"No historical run available"*, berarti Anda belum pernah menjalankan perintah `backtest` atau `optimize` secara sukses. Silakan jalankan perintah tersebut terlebih dahulu di terminal lain.

- **Error "Migration required" saat memeriksa posisi**  
  Anda harus menjalankan `uv run marketpilot migrate --confirm` untuk memperbarui skema *database* lokal (menambahkan kolom *exit_reason*). Tanpanya, fitur Position Manager akan terkunci.

- **Dasbor Tidak Bisa Diakses**  
  Pastikan terminal tempat Anda menjalankan `uv run marketpilot dashboard` masih aktif (tidak terhenti) dan Anda membukanya dari `http://127.0.0.1:8000`, bukan IP publik.

- **Koneksi Bybit / Error Timeout**  
  Jika `uv run marketpilot ping` gagal, periksa apakah komputer Anda memiliki koneksi internet stabil. Jika Anda berada di negara yang memblokir Bybit, koneksi *socket* publik pun mungkin tidak dapat tersambung.

- **Telegram Gagal / Chat ID Salah**  
  Uji konfigurasi dengan `uv run marketpilot telegram test --confirm`. Bila bot tidak mengirimkan pesan, pastikan Anda telah mengirim setidaknya satu pesan (`/start`) ke bot Anda terlebih dahulu agar ia dapat membalas ke *Chat ID* Anda. Cek kembali `TELEGRAM_BOT_TOKEN` di file `.env`.
