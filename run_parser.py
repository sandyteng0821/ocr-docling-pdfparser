"""
run_parser.py — ExcipientBookParser 執行腳本

環境變數：
    PDF_PATH        PDF 檔案路徑          (必填)
    OUTPUT_DIR      輸出資料夾            (預設: extracted_excipients)
    MODE            解析模式              (預設: fast | fast / full / ocr)
    BOOK_VERSION    書的版本              (預設: 5 | 5 / 6)
    PAGE_START      起始頁，0-based       (預設: 不限制)
    PAGE_END        結束頁，0-based       (預設: 不限制)

書本專屬修正請編輯 config.py。
"""

import os
from src.parser import ExcipientBookParser

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from config import NAME_CORRECTIONS, INDEX_CORRECTIONS
except ImportError:
    NAME_CORRECTIONS = {}
    INDEX_CORRECTIONS = {}

# ── 從環境變數讀取參數 ────────────────────────────────────────────────────────

PDF_PATH     = os.environ.get("PDF_PATH")
OUTPUT_DIR   = os.environ.get("OUTPUT_DIR", "extracted_excipients")
MODE         = os.environ.get("MODE", "fast")
BOOK_VERSION = int(os.environ.get("BOOK_VERSION", 5))

_start = os.environ.get("PAGE_START")
_end   = os.environ.get("PAGE_END")
PAGE_RANGE = (int(_start), int(_end)) if _start and _end else None

# ── 執行 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not PDF_PATH:
        raise ValueError("請設定環境變數 PDF_PATH，例如：export PDF_PATH=my.pdf")

    print(f"PDF:        {PDF_PATH}")
    print(f"輸出目錄:   {OUTPUT_DIR}")
    print(f"模式:       {MODE}")
    print(f"書版本:     v{BOOK_VERSION}")
    print(f"頁碼範圍:   {PAGE_RANGE or '全書'}")
    print("-" * 40)

    parser = ExcipientBookParser(
        pdf_path          = PDF_PATH,
        mode              = MODE,
        output_dir        = OUTPUT_DIR,
        page_range        = PAGE_RANGE,
        book_version      = BOOK_VERSION,
        name_corrections  = NAME_CORRECTIONS,
        index_corrections = INDEX_CORRECTIONS,
    )
    parser.run()