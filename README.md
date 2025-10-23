# CR3-Repair-Tool 📷

> Batch utility written in Python for fixing corrupted Canon CR3 (BMFF) raw files. It carves the correct file size by parsing the internal ISO BMFF atom structure (like `mdat` and `ftyp`).

This Python utility is designed to repair corrupted or oversized Canon CR3 (or other ISO Base Media File Format - BMFF) files by accurately determining their logical size. It does this by parsing the file's internal structure (known as **atoms** or **boxes**) and carving out the correct amount of data, leaving behind any corrupt or junk data appended to the end.

The script operates in a **batch mode**, processing all files found within a specified input directory and saving the fixed versions to an output directory.

---

## 🚀 Features

* **Atom Parsing:** Accurately reads and follows the BMFF (ISO/IEC 14496-12) structure, including support for 64-bit size extensions.
* **Batch Processing:** Processes all files in an input folder automatically, ideal for recovering data from damaged memory cards.
* **Atomic Saves:** Uses temporary files (`.tmp`) during the saving process to ensure files are only renamed to the final output name upon successful completion, minimizing data loss risk.
* **Configurable Termination:** Allows specifying the name of the final atom (`--lastchunk`, defaults to `mdat`) to handle different file structures or partial carving requirements.

---

## 📋 Prerequisites

* **Python 3.6+**
* No external libraries are required; the script uses only standard Python libraries.

---

## 💾 Installation and Setup

1.  **Save the script:** Save the provided code as `cr3_fixer.py` (or download it from this repository).
2.  **Create input/output directories:**
    * Create a directory (e.g., `input_files`) and place your corrupted CR3 files inside it.
    * Create an empty directory (e.g., `fixed_files`) where the repaired files will be saved.

---

## 💻 Usage

Run the script from your terminal, specifying the input and output directories:

```bash
python cr3_fixer.py --input-dir /path/to/input_files --output-dir /path/to/fixed_files
