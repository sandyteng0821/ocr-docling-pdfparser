"""
Excipient Book Parser — Docling Version
----------------------------------------
依賴安裝：
    pip install docling

Docling 第一次執行會自動下載 AI 模型（約 300–500 MB），請確保網路連線。

三種解析模式：
    "fast"    - 純文字 PDF，停用 AI 模型，速度最快（等同原本 fitz 版本）
    "full"    - 啟用 Layout + TableFormer，適合含表格的 PDF
    "ocr"     - 強制 OCR，適合掃描版 PDF（需額外安裝 tesseract）

使用方式：
    parser = ExcipientBookParser("Handbook_of_Pharmaceutical_Excipients.pdf", mode="fast")
    parser.run()
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
                 page_range: tuple = None):
        """
        Args:
            pdf_path: PDF 檔案路徑
            mode: 解析模式
                "fast" - 純文字 PDF，停用 AI 模型（預設）
                "full" - 啟用 Layout + TableFormer，適合含表格的 PDF
                "ocr"  - 強制 OCR，適合掃描版 PDF
            output_dir: 輸出資料夾路徑（預設 "extracted_excipients"）
            name_corrections: 命名修正 dict（key: safe_name 小寫, value: 正確名稱）
                              針對特定書籍的排版問題，換書時傳入新的 dict 或留空
            index_corrections: 頁碼修正 dict（key: page index int, value: 正確名稱）
                               針對標題完全不在文字層的特殊頁面
            page_range: 限制解析頁碼範圍，tuple (start, end)，0-based index，
                        例如 (23, 38) 代表第 24–39 頁。預設 None 表示全書。
        """
        self.pdf_path = pdf_path
        self.mode = mode
        self.output_dir = output_dir
        self.name_corrections = name_corrections or {}
        self.index_corrections = index_corrections or {}
        self.page_range = page_range

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.converter = self._build_converter(mode)

    def _build_converter(self, mode: str) -> DocumentConverter:
        """依模式建立對應的 Docling converter"""

        if mode == "fast":
            # 停用所有 AI 模型，速度最快
            # 適合：有文字層的 PDF（本書狀況）
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = False

        elif mode == "full":
            # 啟用 Layout Analysis + TableFormer
            # 適合：含複雜表格的 PDF
            # 注意：第一次執行會下載模型
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE

        elif mode == "ocr":
            # 強制對每頁做 OCR（使用 Tesseract）
            # 適合：掃描版 PDF，或練習比較 OCR vs 文字層的差異
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
        print(f"模式：{self.mode}")
        print(f"開始解析：{self.pdf_path} ...")

        # Docling 一次轉換整份 PDF
        result = self.converter.convert(self.pdf_path)
        doc = result.document

        # 逐頁提取文字（Docling 已處理好分欄順序）
        pages_text = []
        all_pages = list(doc.pages)

        # 套用頁碼範圍限制
        if self.page_range:
            start, end = self.page_range
            all_pages = all_pages[start:end + 1]
            page_offset = start  # 保持 index 與原始頁碼對應
        else:
            page_offset = 0

        for page in all_pages:
            page_no = page if isinstance(page, int) else page.page_no
            page_text = self._extract_page_text(doc, page_no)
            pages_text.append(page_text)

        print(f"共 {len(pages_text)} 頁，開始切割賦形劑...")

        # 以 "1 Nonproprietary Names" 為錨點切割賦形劑
        current_excipient = None
        current_content = []

        for i, page_text in enumerate(pages_text):
            actual_index = i + page_offset  # 對應原始全書的頁碼 index
            # 偵測是否為新藥名的起始點 (Section 1)
            if re.search(r'^\s*1\s+Nonproprietary Names\s*$', page_text, re.MULTILINE):
                # 只要current_excipient 有值，代表前一個成分處理玩了，立刻存檔
                if current_excipient:
                    self.save_to_json(current_excipient, "\n".join(current_content))
                    # 存檔後清空內容準備接下一個
                    current_content = []

                # 嘗試從當前頁第一行取得藥名
                first_line = page_text.split('\n')[0].strip()

                # 如果第一行就是錨點，代表頁面標題不在文字層（圖片化標題）
                # 改從 Section 1 Nonproprietary Names 的內容反推藥名
                if not first_line or re.match(r'^\s*1\s+Nonproprietary Names\s*$', first_line):
                    first_line = self._extract_name_from_section1(page_text)
                    if not first_line:
                        first_line = f"Unknown_{actual_index}"

                # index 直接對應修正（處理標題完全無法從文字層取得的特殊頁面）
                if actual_index in self.index_corrections:
                    first_line = self.index_corrections[actual_index]

                # 過濾 Docling 圖片佔位符
                if "imagenotavailable" in "".join(c for c in first_line if c.isalnum()).lower():
                    first_line = f"Unknown_{actual_index}"

                # 移除尾端標點（如 'Alitame.' → 'Alitame'）
                first_line = first_line.rstrip('.,;:')

                # 修正前綴 'a' 的排版問題（如 'aDichlorodifluoromethane...'）
                if re.match(r'^a[A-Z]', first_line):
                    first_line = first_line[1:]

                # 套用已知修正
                safe_check = "".join(c for c in first_line if c.isalnum()).lower()
                if safe_check in self.name_corrections:
                    first_line = self.name_corrections[safe_check]

                current_excipient = first_line if first_line else f"Unknown_{actual_index}"
                current_content.append(page_text) # 加入第一頁內容
                print(f"  發現新賦形劑: {current_excipient} (第 {actual_index + 1} 頁)")
            else:
                if current_excipient:
                    current_content.append(page_text)

        # 存最後一個
        if current_excipient:
            self.save_to_json(current_excipient, "\n".join(current_content))

        print("完成！")

    def _extract_name_from_section1(self, page_text: str) -> str:
        """
        當頁面標題不在文字層時，從 Section 1 內容反推藥名。
        處理以下格式：
          - 'JP: Agar'                              → Agar
          - 'BP: Sucrose JP: Sucrose ...'            → Sucrose
          - 'BP: Hypromellose phthalate JP: ...'    → Hypromellose Phthalate
          - '(a) USPNF: Butane'                     → 群組型，取括號內容
          - 'See Table I.'                           → 群組型，從內文找
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
            # 群組型條目（如 Aliphatic Polyesters）：從內文找粗體標題
            # 通常在 Section 6 Functional Category 前後有群組名
            for line in lines:
                if re.match(r'^\s*6\s+Functional Category', line):
                    break
                # 跳過章節標題和短行
                if re.match(r'^\s*\d+\s+[A-Z]', line):
                    continue
                if len(line) > 5 and not re.search(r'[:;,\(\)]', line):
                    return line
            return ""

        # 處理 '(a) USPNF: Butane' 格式（群組型）
        grouped = re.match(r'^\([a-z]\)\s+(?:BP|JP|PhEur|USPNF|USP|NF|BPC):\s*(.+)', section1_line)
        if grouped:
            # 取父級名稱需從 Section 6 或內文找，暫時回傳第一個子項名
            return grouped.group(1).strip().split()[0]

        # 所有藥典縮寫
        pharmacopeias = r'(?:BP|JP|PhEur|USPNF|USP|NF|BPC|PhInt)'

        # 從 'BP: Name JP: OtherName PhEur: LatinName' 取出所有名稱
        matches = re.findall(
            rf'(?:{pharmacopeias}):\s*([A-Za-z][\w\s,\-\(\)/]+?)(?=\s+{pharmacopeias}:|$)',
            section1_line
        )
        if matches:
            # 過濾掉拉丁文名稱（含小寫結尾 -um/-us/-is/-ae），取最短的英文名
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
        Docling 已處理好閱讀順序（包含雙欄排版），不需要手動排序。
        """
        texts = []
        for element, _ in doc.iterate_items(page_no=page):
            # 取出文字內容（支援 TextItem、TableItem 等）
            if hasattr(element, "text") and element.text:
                texts.append(element.text)
            elif hasattr(element, "export_to_markdown"):
                try:
                    texts.append(element.export_to_markdown(doc))
                except TypeError:
                    pass  # PictureItem 等非文字元素略過
        return "\n".join(texts)

    def save_to_json(self, name: str, full_text: str):
            """將提取出的文字進行章節切割並存檔（包含檔名長度熔斷機制）"""
            
            # 1. 內部章節切割邏輯
            sections = re.split(r'(?m)^\s*(\d{1,2})\s+([A-Z][a-zA-Z\s]+?)\s*$', full_text)
            data = {"name": name, "sections": {}}

            for i in range(1, len(sections), 3):
                if i + 2 >= len(sections):
                    break
                num = sections[i]
                title = sections[i + 1].strip()
                content = sections[i + 2].strip()
                data["sections"][f"{num}_{title}"] = content

            # 2. 處理檔名：防止出現 OSError [Errno 36] File name too long
            # 只保留字母、數字、底線與空格
            clean_name = "".join([c for c in name if c.isalnum() or c in (' ', '_')]).strip()
            
            # 熔斷機制：如果名字長度超過 50，通常是誤抓了內文，強制截斷並標記
            if len(clean_name) > 50:
                print(f"⚠️ 偵測到異常超長藥名，已進行截斷處理。")
                safe_name = clean_name[:45] + "_TRUNC"
            elif not clean_name:
                safe_name = "Unknown_Excipient"
            else:
                safe_name = clean_name

            # 3. 執行存檔
            file_path = os.path.join(self.output_dir, f"{safe_name}.json")
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            except OSError as e:
                # 如果還是失敗（極端情況），改用時間戳或簡單標籤存檔，確保程式不崩潰
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
    # name_corrections / index_corrections 針對此書的排版特殊情況
    parser = ExcipientBookParser(
        _pdf,
        page_range=(24, 39),
        mode="fast",
        output_dir=_output_dir,
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

    # 其他版本的書 → 不帶 corrections，乾淨跑，視情況再補
    # parser = ExcipientBookParser(
    #     "Handbook_v6.pdf",
    #     mode="full",
    #     output_dir="extracted_v6"
    # )