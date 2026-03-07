# 使用官方 Python Slim 映像檔作為基底，兼顧體積與相容性
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 1. 安裝系統級依賴 (重要：Docling 與 OCR 運作所需)
# libgl1: OpenCV 所需
# libgomp1: ONNX Runtime 加速所需
# tesseract-ocr: mode="ocr" 所需
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    tesseract-ocr \
    libtesseract-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. 複製 requirements.txt 並安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# [選配] 如果要在容器內預下載模型 (避免執行時下載過久)
# RUN python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"

# 3. 複製專案程式碼
COPY . .

# 4. 建立輸出目錄並給予權限
RUN mkdir -p extracted_docling && chmod 777 extracted_docling

# 環境變數設定
ENV PYTHONUNBUFFERED=1
ENV PDF_PATH="Handbook_of_Pharmaceutical_Excipients.pdf"
ENV OUTPUT_DIR="extracted_docling"

# 啟動命令
CMD ["python", "parser.py"]