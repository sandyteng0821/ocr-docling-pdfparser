# ocr-docling-pdfparser

A PDF parser for extracting pharmaceutical excipient monographs from the *Handbook of Pharmaceutical Excipients* into structured JSON files.

Built on [Docling](https://github.com/DS4SD/docling) for PDF parsing, with support for multiple editions of the handbook.

---

## How It Works

The parser scans each page for `1 Nonproprietary Names` as an anchor point to detect the start of a new excipient entry. It then extracts the excipient name and splits the full text into numbered sections (e.g. `2_Synonyms`, `6_Functional Category`), saving each entry as a JSON file.

---

## Output Format

Each excipient is saved as `<ExcipientName>.json`:

```json
{
    "name": "Acesulfame Potassium",
    "sections": {
        "1_Nonproprietary Names": "BP: Acesulfame Potassium ...",
        "2_Synonyms": "Acesulfame K; ace K; ...",
        "6_Functional Category": "Sweetening agent.",
        "14_Safety": "LD50 (rat, oral): 6.9-8.0 g/kg ..."
    }
}
```

---

## Installation

### Local

```bash
pip install -r requirements.txt
```

> Docling will automatically download AI models (~300–500 MB) on first run when using `full` or `ocr` mode.

### Docker

```bash
# Build
docker build -t excipient-parser .

# Run — mount a local directory to retrieve output files
docker run --rm \
  -e PDF_PATH=/data/Handbook_of_Pharmaceutical_Excipients.pdf \
  -e OUTPUT_DIR=/data/output \
  -e MODE=full \
  -e BOOK_VERSION=6 \
  -v /your/local/path:/data \
  excipient-parser python run_parser.py
```

To pre-download Docling models inside the image (avoids slow first-run downloads), uncomment this line in the Dockerfile:

```dockerfile
RUN python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"
```

---

## Usage

### 1. Configure via `.env`

Copy the example and fill in your values:

```bash
cp env.example .env
```

```dotenv
PDF_PATH=Handbook_of_Pharmaceutical_Excipients.pdf
OUTPUT_DIR=extracted_excipients
MODE=fast
BOOK_VERSION=5
# PAGE_START=24
# PAGE_END=39
```

### 2. Configure book-specific corrections in `config.py`

`config.py` holds name corrections and page index overrides for known parsing issues (e.g. image-based titles, layout quirks specific to an edition). When switching to a new book, clear both dicts and re-populate as needed.

```python
NAME_CORRECTIONS = {
    "seetablei": "Aliphatic Polyesters",
    "agar":      "Agar",
    # ...
}

INDEX_CORRECTIONS = {
    29: "Acacia",   # image-based title, cannot be extracted from text layer
    35: "Acetone",
}
```

### 3. Run

```bash
python3 run_parser.py
```

To run in the background without the terminal staying open:

```bash
# Mac
caffeinate -i python3 run_parser.py > parser.log 2>&1 &

# Linux
nohup python3 run_parser.py > parser.log 2>&1 &

# Follow progress
tail -f parser.log
```

---

## Parsing Modes

| Mode | Description | When to use |
|------|-------------|-------------|
| `fast` | Text extraction only, no AI models | Standard text-layer PDFs (fastest) |
| `full` | Layout analysis + TableFormer | PDFs with complex tables |
| `ocr` | Force OCR via Tesseract | Scanned PDFs |

---

## Book Version Differences

| `book_version` | Name extraction strategy |
|----------------|--------------------------|
| `5` | Excipient name is the first line of the page |
| `6` | Excipient name is a `SectionHeaderItem` appearing before the anchor; falls back to v5 logic if not found |

---

## Project Structure

```
.
├── src/
│   └── parser.py           # ExcipientBookParser class
├── run_parser.py           # Entry point, reads config from .env
├── config.py               # Book-specific name/index corrections
├── config-example-v5.py    # Example corrections for v5 handbook
├── env.example             # Environment variable template
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container build definition
└── README.md
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PDF_PATH` | — | Path to the PDF (**required**) |
| `OUTPUT_DIR` | `extracted_excipients` | Output directory |
| `MODE` | `fast` | Parsing mode: `fast` / `full` / `ocr` |
| `BOOK_VERSION` | `5` | Handbook edition: `5` or `6` |
| `PAGE_START` | — | Start page, 0-based (optional) |
| `PAGE_END` | — | End page, 0-based (optional) |