"""
Excipient Book Parser — Docling Version
----------------------------------------
依賴安裝：
    pip install docling

三種解析模式：
    "fast"    - 純文字 PDF，停用 AI 模型，速度最快
    "full"    - 啟用 Layout + TableFormer，適合含表格的 PDF
    "ocr"     - 強制 OCR，適合掃描版 PDF（需額外安裝 tesseract）

book_version 差異：
    5 - 藥名是頁面第一行（或從 Section 1 內容反推）
    6 - 藥名是 SectionHeaderItem，出現在錨點之前；fallback 同 v5
"""

import re
import json
import os
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions, TableFormerMode,
    TesseractCliOcrOptions
)
from docling.datamodel.base_models import InputFormat


class ExcipientBookParser:
    def __init__(self, pdf_path: str, mode: str = "fast", output_dir: str = "extracted_excipients",
                 name_corrections: dict = None, index_corrections: dict = None,
                 page_range: tuple = None, book_version: int = 5):
        """
        Args:
            pdf_path: PDF 檔案路徑
            mode: 解析模式 "fast" / "full" / "ocr"
            output_dir: 輸出資料夾路徑
            name_corrections: 命名修正 dict（key: safe_name 小寫, value: 正確名稱）
            index_corrections: 頁碼修正 dict（key: page index int, value: 正確名稱）
            page_range: tuple (start, end)，0-based index，預設 None 表示全書
            book_version: 5 或 6，影響藥名抓取邏輯（預設 5）
        """
        self.pdf_path = pdf_path
        self.mode = mode
        self.output_dir = output_dir
        self.name_corrections = name_corrections or {}
        self.index_corrections = index_corrections or {}
        self.page_range = page_range
        self.book_version = book_version

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.converter = self._build_converter(mode)

    def _build_converter(self, mode: str) -> DocumentConverter:
        if mode == "fast":
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = False

        elif mode == "full":
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE

        elif mode == "ocr":
            ocr_options = TesseractCliOcrOptions(lang=["eng"])
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            pipeline_options.do_table_structure = False
            pipeline_options.ocr_options = ocr_options

        else:
            raise ValueError(f"未知模式：{mode}，請使用 'fast'、'full' 或 'ocr'")

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

    def run(self):
        print(f"模式：{self.mode}  書版本：v{self.book_version}")
        print(f"開始解析：{self.pdf_path} ...")

        result = self.converter.convert(self.pdf_path)
        doc = result.document

        pages_text = []
        all_pages = list(doc.pages)

        if self.page_range:
            start, end = self.page_range
            all_pages = all_pages[start:end + 1]
            page_offset = start
        else:
            page_offset = 0

        for page in all_pages:
            page_no = page if isinstance(page, int) else page.page_no
            page_text = self._extract_page_text(doc, page_no)
            pages_text.append(page_text)

        print(f"共 {len(pages_text)} 頁，開始切割賦形劑...")

        current_excipient = None
        current_content = []

        for i, page_text in enumerate(pages_text):
            actual_index = i + page_offset

            if re.search(r'^\s*1\s+Nonproprietary Names\s*$', page_text, re.MULTILINE):
                if current_excipient:
                    self.save_to_json(current_excipient, "\n".join(current_content))
                    current_content = []
                # 掃整頁找 __HEADER__ 標記（v6 藥名可能不在第一行）
                header_match = re.search(r'^__HEADER__ (.+)$', page_text, re.MULTILINE)
                if header_match:
                    first_line = header_match.group(1).strip()
                else:
                    # 嘗試從當前頁第一行取得藥名
                    first_line = page_text.split('\n')[0].strip()
                    if not first_line or re.match(r'^\s*1\s+Nonproprietary Names\s*$', first_line):
                        # v5 原本邏輯，同時也是 v6 的 fallback
                        first_line = self._extract_name_from_section1(page_text)
                        if not first_line:
                            first_line = f"Unknown_{actual_index}"

                # index 直接對應修正
                if actual_index in self.index_corrections:
                    first_line = self.index_corrections[actual_index]

                # 過濾 Docling 圖片佔位符
                if "imagenotavailable" in "".join(c for c in first_line if c.isalnum()).lower():
                    first_line = f"Unknown_{actual_index}"

                # 移除尾端標點
                first_line = first_line.rstrip('.,;:')

                # 修正前綴 'a' 的排版問題
                if re.match(r'^a[A-Z]', first_line):
                    first_line = first_line[1:]

                # 套用已知修正
                safe_check = "".join(c for c in first_line if c.isalnum()).lower()
                if safe_check in self.name_corrections:
                    first_line = self.name_corrections[safe_check]

                current_excipient = first_line if first_line else f"Unknown_{actual_index}"
                current_content.append(page_text)
                print(f"  發現新賦形劑: {current_excipient} (第 {actual_index + 1} 頁)")
            else:
                if current_excipient:
                    current_content.append(page_text)

        if current_excipient:
            self.save_to_json(current_excipient, "\n".join(current_content))

        print("完成！")

    def _extract_name_from_section1(self, page_text: str) -> str:
        """
        v5 主要路徑，同時作為 v6 的 fallback。
        從 Section 1 內容反推藥名，處理以下格式：
          - 'JP: Agar'                           → Agar
          - 'BP: Sucrose JP: Sucrose ...'         → Sucrose
          - 'BP: Hypromellose phthalate JP: ...' → Hypromellose Phthalate
          - '(a) USPNF: Butane'                  → 群組型
          - 'See Table I.'                        → 群組型，從內文找
        """
        lines = [l.strip() for l in page_text.split('\n') if l.strip()]

        section1_line = ""
        for line in lines:
            if re.match(r'^\s*1\s+Nonproprietary Names\s*$', line):
                continue
            if re.match(r'^\s*2\s+', line):
                break
            section1_line = line
            break

        if not section1_line or section1_line == "See Table I.":
            for line in lines:
                if re.match(r'^\s*6\s+Functional Category', line):
                    break
                if re.match(r'^\s*\d+\s+[A-Z]', line):
                    continue
                if len(line) > 5 and not re.search(r'[:;,\(\)]', line):
                    return line
            return ""

        grouped = re.match(r'^\([a-z]\)\s+(?:BP|JP|PhEur|USPNF|USP|NF|BPC):\s*(.+)', section1_line)
        if grouped:
            return grouped.group(1).strip().split()[0]

        pharmacopeias = r'(?:BP|JP|PhEur|USPNF|USP|NF|BPC|PhInt)'
        matches = re.findall(
            rf'(?:{pharmacopeias}):\s*([A-Za-z][\w\s,\-\(\)/]+?)(?=\s+{pharmacopeias}:|$)',
            section1_line
        )
        if matches:
            english_names = [
                m.strip() for m in matches
                if not re.search(r'(?:um|us|is|ae|ium)\s*$', m.strip(), re.IGNORECASE)
            ]
            candidates = english_names if english_names else [m.strip() for m in matches]
            return min(candidates, key=len)

        return ""

    def _extract_page_text(self, doc, page) -> str:
        """
        從 Docling page 物件提取純文字。
        v6 模式下，非章節編號的 SectionHeaderItem（即藥名）加上 __HEADER__ 前綴；
        章節標題（數字開頭，如 "1 Nonproprietary Names"）保持原樣，不影響錨點偵測。
        """
        texts = []
        for element, _ in doc.iterate_items(page_no=page):
            if hasattr(element, "text") and element.text:
                if (self.book_version >= 6
                        and type(element).__name__ == "SectionHeaderItem"
                        and not re.match(r'^\d+\s+', element.text)):
                    # 非章節編號的 header = 藥名，加標記
                    texts.append(f"__HEADER__ {element.text}")
                else:
                    texts.append(element.text)
            elif hasattr(element, "export_to_markdown"):
                try:
                    texts.append(element.export_to_markdown(doc))
                except TypeError:
                    pass
        return "\n".join(texts)

    def save_to_json(self, name: str, full_text: str):
        """將提取出的文字進行章節切割並存檔（包含檔名長度熔斷機制）"""

        # __HEADER__ 標記只是內部用，存檔前清掉
        clean_text = re.sub(r'^__HEADER__ ', '', full_text, flags=re.MULTILINE)

        sections = re.split(r'(?m)^\s*(\d{1,2})\s+([A-Z][a-zA-Z\s]+?)\s*$', clean_text)
        data = {"name": name, "sections": {}}

        for i in range(1, len(sections), 3):
            if i + 2 >= len(sections):
                break
            num = sections[i]
            title = sections[i + 1].strip()
            content = sections[i + 2].strip()
            data["sections"][f"{num}_{title}"] = content

        clean_name = "".join([c for c in name if c.isalnum() or c in (' ', '_')]).strip()

        if len(clean_name) > 50:
            print(f"⚠️ 偵測到異常超長藥名，已進行截斷處理。")
            safe_name = clean_name[:45] + "_TRUNC"
        elif not clean_name:
            safe_name = "Unknown_Excipient"
        else:
            safe_name = clean_name

        file_path = os.path.join(self.output_dir, f"{safe_name}.json")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except OSError:
            alt_path = os.path.join(self.output_dir, f"error_fallback_{hash(name)}.json")
            with open(alt_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"❌ 嚴重檔名錯誤，已使用備用名存檔: {alt_path}")

    def save_to_json_v5(self, name: str, full_text: str):
        """將提取出的文字進行章節切割並存檔（邏輯與原版相同）"""
        sections = re.split(r'(?m)^\s*(\d{1,2})\s+([A-Z][a-zA-Z\s]+?)\s*$', full_text)

        data = {"name": name, "sections": {}}

        for i in range(1, len(sections), 3):
            if i + 2 >= len(sections):
                break
            num = sections[i]
            title = sections[i + 1].strip()
            content = sections[i + 2].strip()
            data["sections"][f"{num}_{title}"] = content

        safe_name = "".join([c for c in name if c.isalnum()])
        file_path = os.path.join(self.output_dir, f"{safe_name}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)


# ── 執行 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os as _os
    _pdf = _os.environ.get("PDF_PATH", "Handbook_of_Pharmaceutical_Excipients.pdf")
    _output_dir = _os.environ.get("OUTPUT_DIR", "extracted_docling")

    # Handbook of Pharmaceutical Excipients 第五版
    parser = ExcipientBookParser(
        _pdf,
        page_range=(24, 39),
        mode="fast",
        output_dir=_output_dir,
        book_version=5,
        name_corrections={
            "seetablei":            "Aliphatic Polyesters",
            "butane":               "Hydrocarbons HC",
            "kaliicitras":          "Potassium Citrate",
            "hypromellosiphthalas": "Hypromellose Phthalate",
            "saccharinsodium":      "Saccharin Sodium",
            "sulfobutyletherbbcyclodextrin": "Sulfobutylether b-Cyclodextrin",
            "agar":                 "Agar",
            "alitame":              "Alitame",
            "adichlorodifluoromethanepropellant12": "Chlorofluorocarbons CFC",
        },
        index_corrections={
            36: "Agar",
            50: "Alitame",
        }
    )
    parser.run()