import os
import re
import time as pytime
import requests
import calendar
from datetime import datetime, date, timedelta, timezone
from github import Github, GithubException

# ==========================
# KONFIGURASI UTAMA
# ==========================
GITHUB_TOKEN = os.getenv('GITHUB_PAT')  # Ambil dari environment variable

# Sumber konten (tanpa footer). Kita akan tambahkan footer sendiri.
SOURCE_URL   = "https://raw.githubusercontent.com/Xaffin/-/refs/heads/main/%E0%B8%AD%E0%B8%B1%E0%B8%9F%E0%B8%9F%E0%B8%B4%E0%B8%99"

# REPO tujuan (Format: "username/repository")
DEST_REPO    = "uppermoon77/bodyslam"
GIT_BRANCH   = "main"
COMMIT_MSG   = "Auto update: Sync playlist from source + footer update"
SLEEP_BETWEEN_COMMITS_SEC = 0.7

# Mode expired per FILE NAME (bukan per repo)
EXPIRE_HOUR_LOCAL = 13    # 13:00 WIB
EXPIRE_MINUTE_LOCAL = 0

# Saat expired (global), kita bisa tulis marker ini (opsional)
SYNC_DISABLED_MARKER = ".SYNC_DISABLED"
HONOR_MARKER_EVEN_BEFORE_EXPIRY = False  # set True jika ingin hormati marker walau belum expired

# ==========================
# UTIL TANGGAL & WIB
# ==========================
JAKARTA_TZ = timezone(timedelta(hours=7))

def now_jakarta() -> datetime:
    return datetime.now(tz=JAKARTA_TZ)

def expiry_cutoff(dt: date) -> datetime:
    """Expire pada Hari-H pukul EXPIRE_HOUR_LOCAL:EXPIRE_MINUTE_LOCAL WIB."""
    return datetime(dt.year, dt.month, dt.day, EXPIRE_HOUR_LOCAL, EXPIRE_MINUTE_LOCAL, tzinfo=JAKARTA_TZ)

# ==========================
# PARSER TANGGAL DARI NAMA (FILE)
# ==========================
ID_MONTHS = {
    "JANUARI": 1, "FEBRUARI": 2, "MARET": 3, "APRIL": 4, "MEI": 5, "JUNI": 6,
    "JULI": 7, "AGUSTUS": 8, "SEPTEMBER": 9, "OKTOBER": 10, "NOVEMBER": 11, "DESEMBER": 12
}

def parse_date_from_name(name: str) -> date | None:
    """
    Coba berbagai pola tanggal di NAMA FILE:
    1) DC21NOVEMBER2025 / 21NOVEMBER2025 (DD<BULAN_ID>YYYY) -- case-insensitive
    2) 21-11-2025 | 21_11_2025 | 21.11.2025 | 21/11/2025
    3) 2025-11-21 | 2025_11_21
    4) 8 digit rapat: YYYYMMDD atau DDMMYYYY
    """
    name = name.upper()

    # Pola 1
    m = re.search(r'(\d{1,2})(JANUARI|FEBRUARI|MARET|APRIL|MEI|JUNI|JULI|AGUSTUS|SEPTEMBER|OKTOBER|NOVEMBER|DESEMBER)(\d{4})', name, re.IGNORECASE)
    if m:
        dd = int(m.group(1))
        mm = ID_MONTHS[m.group(2).upper()]
        yyyy = int(m.group(3))
        try:
            return date(yyyy, mm, dd)
        except ValueError:
            pass

    # Pola 2: DD[-_./]MM[-_./]YYYY
    m = re.search(r'(\d{1,2})[-_./](\d{1,2})[-_./](\d{4})', name)
    if m:
        dd = int(m.group(1)); mm = int(m.group(2)); yyyy = int(m.group(3))
        try:
            return date(yyyy, mm, dd)
        except ValueError:
            pass

    # Pola 3: YYYY[-_./]MM[-_./]DD
    m = re.search(r'(\d{4})[-_./](\d{1,2})[-_./](\d{1,2})', name)
    if m:
        yyyy = int(m.group(1)); mm = int(m.group(2)); dd = int(m.group(3))
        try:
            return date(yyyy, mm, dd)
        except ValueError:
            pass

    # Pola 4: 8 digit rapat
    m = re.search(r'(\d{8})', name)
    if m:
        digits = m.group(1)
        # Coba YYYYMMDD
        try:
            yyyy = int(digits[0:4]); mm = int(digits[4:6]); dd = int(digits[6:8])
            return date(yyyy, mm, dd)
        except ValueError:
            pass
        # Coba DDMMYYYY
        try:
            dd  = int(digits[0:2]); mm = int(digits[2:4]); yyyy = int(digits[4:8])
            return date(yyyy, mm, dd)
        except ValueError:
            pass

    return None

def is_expired_by_name(name: str) -> bool:
    """
    True jika sekarang (WIB) >= Hari-H 13:00, berdasar tanggal yang ditemukan di NAMA FILE.
    Contoh nama: DC21OKTOBER2025 → expired mulai 21-10-2025 13:00 WIB.
    """
    dt = parse_date_from_name(name)
    if not dt:
        print(f"⚠️  Tidak menemukan tanggal di nama '{name}'. Lewati expiry per-file.")
        return False
    cutoff = expiry_cutoff(dt)
    now_ = now_jakarta()
    print(f"ℹ️  File date = {dt.isoformat()} | Cutoff = {cutoff.isoformat()} | Now = {now_.isoformat()}")
    return now_ >= cutoff

# ==========================
# FOOTER & TEMPLATE
# ==========================
FOOTER_REGEX = r'(?mi)^\s*#EXTM3U\s+billed-msg="[^"]+"\s*$'

def generate_footer(dest_file_path: str, expired: bool) -> str:
    if expired:
        return '#EXTM3U billed-msg="MASA BERLAKU HABIS| lynk.id/magelife😎"'
    return f'#EXTM3U billed-msg="😎{dest_file_path}| lynk.id/magelife😎"'

def strip_footer(text: str) -> str:
    return re.sub(FOOTER_REGEX, '', text).strip()

def add_footer(text: str, dest_file_path: str, expired: bool) -> str:
    cleaned = strip_footer(text)
    return f"{cleaned}\n\n{generate_footer(dest_file_path, expired)}\n"

def build_expired_playlist_block() -> str:
    return (
        '#EXTINF:-1 group-logo="https://i.imgur.com/aVBedkE.jpeg",🔰 MAGELIFE OFFICIAL\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/CctbVah.jpeg" group-title="🔰 MAGELIFE OFFICIAL", MASA BERLAKU HABIS\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/XXQ2pQ3.jpeg", ❌ MASA BERLAKU HABIS\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/XXQ2pQ3.jpeg" group-title="❌ MASA BERLAKU HABIS", MASA BERLAKU HABIS\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/XXQ2pQ3.jpeg", ❌ MASA BERLAKU HABIS OM\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/XXQ2pQ3.jpeg" group-title="❌ MASA BERLAKU HABIS OM", MASA BERLAKU HABIS\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/XXQ2pQ3.jpeg", ❌ MASA BERLAKU HABIS TANTE\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/XXQ2pQ3.jpeg" group-title="❌ MASA BERLAKU HABIS TANTE", MASA BERLAKU HABIS\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/bjfYe6g.jpeg", ✅ SILAHKAN RE ORDER\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/bjfYe6g.jpeg" group-title="✅ SILAHKAN RE ORDER", SILAHKAN RE ORDER\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/bjfYe6g.jpeg", ✅SILAHKAN RE ORDER OM\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/bjfYe6g.jpeg" group-title="✅ SILAHKAN RE ORDER OM", SILAHKAN RE ORDER\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/bjfYe6g.jpeg", ✅SILAHKAN RE ORDER TANTE\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/bjfYe6g.jpeg" group-title="✅ SILAHKAN RE ORDER TANTE", SILAHKAN RE ORDER\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/bjfYe6g.jpeg", 📲 Wa 082219213334\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/bjfYe6g.jpeg" group-title="📲 Wa 082219213334", SILAHKAN RE ORDER\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/bjfYe6g.jpeg", 📲 Wa 082219213334 order\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/bjfYe6g.jpeg" group-title="📲 Wa 082219213334 order", SILAHKAN RE ORDER\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/PJ9tRpK.jpeg",✅ ORDER LYNK\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/PJ9tRpK.jpeg" group-title="✅ ORDER LYNK", ORDER LYNK\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/PJ9tRpK.jpeg",✅ https://lynk.id/magelife\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/PJ9tRpK.jpeg" group-title="✅ https://lynk.id/magelife", ORDER SHOPEE\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/PJ9tRpK.jpeg", ✅ORDER SHOPEE \n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/EWttwBZ.jpeg" group-title="✅ ORDER SHOPEE", ORDER LYNK\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n\n'
        '#EXTINF:-1 group-logo="https://i.imgur.com/PJ9tRpK.jpeg", ✅ https://shorturl.at/1r9BB\n\n'
        '#EXTINF:-1 tvg-id="Iheart80s" tvg-name="Iheart80s" tvg-logo="https://i.imgur.com/EWttwBZ.jpeg" group-title="✅ https://shorturl.at/1r9BB", ORDER LYNK\n'
        'https://iheart-iheart80s-1-us.roku.wurl.tv/playlist.m3u8\n'
    )

# ==========================
# AMBIL KONTEN (HANYA SAAT BELUM EXPIRED)
# ==========================
def get_source_content() -> str | None:
    try:
        print(f"Mengambil konten dari: {SOURCE_URL} ...")
        headers = {"User-Agent": "MagelifeSync/1.0 (+https://lynk.id/magelife)"}
        r = requests.get(SOURCE_URL, timeout=30, headers=headers)
        r.raise_for_status()
        print("✅ Konten berhasil diambil.")
        return r.text
    except requests.exceptions.RequestException as e:
        print(f"❌ Gagal mengambil konten sumber: {e}")
        return None

# ==========================
# GITHUB HELPER
# ==========================
def ensure_marker(repo):
    """Buat marker global kalau ingin mengunci sync (opsional)."""
    try:
        repo.get_contents(SYNC_DISABLED_MARKER, ref=GIT_BRANCH)
        print(f"ℹ️  Marker {SYNC_DISABLED_MARKER} sudah ada.")
    except GithubException as e:
        if getattr(e, "status", None) == 404:
            print(f"📝 Membuat marker {SYNC_DISABLED_MARKER} ...")
            repo.create_file(
                path=SYNC_DISABLED_MARKER,
                message="Mark: sync disabled (manual/opsional)",
                content=f"Marked at {now_jakarta().isoformat()} WIB\n",
                branch=GIT_BRANCH
            )
            print("✅ Marker dibuat.")
        else:
            print(f"⚠️  Tidak bisa cek/buat marker: {e}")

def repo_has_marker(repo) -> bool:
    try:
        repo.get_contents(SYNC_DISABLED_MARKER, ref=GIT_BRANCH)
        return True
    except GithubException:
        return False

# ==========================
# TARGET FILES (dinamis per bulan/tahun)
# ==========================
def generate_target_files(
    month_name: str = "AGUSTUS",
    year: int = 2026,
    prefix: str = "BS",
) -> list[str]:
    """
    Menghasilkan OA01<BULAN><TAHUN> ... OA<DD><BULAN><TAHUN> sesuai jumlah hari pada bulan-tahun.
    """
    month_name = month_name.upper()
    if month_name not in ID_MONTHS:
        raise ValueError(f"Bulan '{month_name}' tidak dikenal. Gunakan salah satu: {', '.join(ID_MONTHS.keys())}")

    month_num = ID_MONTHS[month_name]
    days_in_month = calendar.monthrange(year, month_num)[1]
    return [f"{prefix}{day:02d}{month_name}{year}" for day in range(1, days_in_month + 1)]

# ==========================
# UPDATE FILE PER ITEM
# ==========================
def update_single_file(g: Github, dest_file_path: str, base_content_no_footer: str, force_expired: bool | None = None) -> None:
    """
    force_expired: paksa expired (True) / paksa aktif (False) / None = auto by file name
    """
    repo = g.get_repo(DEST_REPO)
    expired_now = is_expired_by_name(dest_file_path) if force_expired is None else force_expired

    content_body = build_expired_playlist_block() if expired_now else base_content_no_footer
    new_content_with_footer = add_footer(content_body, dest_file_path, expired_now)

    print(f"\n🟦 Memproses file: {dest_file_path} (expired={expired_now})")

    try:
        contents = repo.get_contents(dest_file_path, ref=GIT_BRANCH)
        sha = contents.sha
        old_text = contents.decoded_content.decode("utf-8")
        old_no_footer = strip_footer(old_text)

        # Cek perubahan (tanpa footer)
        if old_no_footer.strip() == content_body.strip():
            print("➡️  Tidak ada perubahan, skip.")
            return

        print("✏️  Ada perubahan, memperbarui file...")
        repo.update_file(
            path=contents.path,
            message=COMMIT_MSG,
            content=new_content_with_footer,
            sha=sha,
            branch=GIT_BRANCH
        )
        print("✅ File berhasil di-update!")

    except GithubException as e:
        if getattr(e, "status", None) == 404:
            print("🆕 File belum ada, membuat baru...")
            repo.create_file(
                path=dest_file_path,
                message=COMMIT_MSG,
                content=new_content_with_footer,
                branch=GIT_BRANCH
            )
            print("✅ File baru berhasil dibuat.")
        else:
            print(f"❌ Error API GitHub: {e}")
    except Exception as e:
        print(f"❌ Error tak terduga: {e}")

# ==========================
# MAIN
# ==========================
def main():
    if not GITHUB_TOKEN:
        print("❌ Error: environment variable GITHUB_PAT belum diatur.")
        return

    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(DEST_REPO)

    # Opsional: hormati marker global?
    if HONOR_MARKER_EVEN_BEFORE_EXPIRY and repo_has_marker(repo):
        print(f"⛔ Ditemukan marker {SYNC_DISABLED_MARKER}. Auto sync dimatikan untuk semua file.")
        force_expired = True
        base_no_footer = ""
    else:
        src = get_source_content()
        if src is None:
            print("❌ Gagal ambil sumber. Stop.")
            return
        base_no_footer = strip_footer(src)
        force_expired = None  # auto per-file

    # Proses semua file target
    target_files = generate_target_files(month_name="AGUSTUS", year=2026, prefix="BS")
    print(f"\n📁 Daftar file target ({len(target_files)}):")
    print(target_files)

    for idx, dest_file_path in enumerate(target_files, start=1):
        print(f"\n({idx}/{len(target_files)}) Mulai update {dest_file_path}...")
        update_single_file(g, dest_file_path, base_no_footer, force_expired=force_expired)
        pytime.sleep(SLEEP_BETWEEN_COMMITS_SEC)

    print("\n🎯 Semua file selesai diproses!")

if __name__ == "__main__":
    main()
