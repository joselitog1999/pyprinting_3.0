import os
from pypdf import PdfReader

PDF_DIR = r"c:\Users\josel\Documents\Obsidian_Vault\printing3\docs\bibliografia"
OUTPUT_DIR = r"c:\Users\josel\Documents\Obsidian_Vault\printing3\scratch"

def extract_gargiulo_chapters():
    path = os.path.join(PDF_DIR, "Julian_Gargiulo_2017.pdf")
    reader = PdfReader(path)
    
    with open(os.path.join(OUTPUT_DIR, "gargiulo_ch3_ch4_ch5.txt"), "w", encoding="utf-8") as f:
        f.write("=== JULIAN GARGIULO (2017) - CHAPTERS 3, 4, 5, 6 ===\n\n")
        # Extract pages 35 to 95
        for p in range(35, min(95, len(reader.pages))):
            f.write(f"\n--- PAGE {p+1} ---\n")
            text = reader.pages[p].extract_text() or ""
            f.write(text + "\n")

def extract_martinez_chapters():
    path = os.path.join(PDF_DIR, "Tesis Luciana Martinez.pdf")
    reader = PdfReader(path)
    
    with open(os.path.join(OUTPUT_DIR, "martinez_chapters.txt"), "w", encoding="utf-8") as f:
        f.write("=== LUCIANA MARTINEZ - ÍNDICE Y CAPÍTULOS PRINCIPALES ===\n\n")
        # Extract first 15 pages (index) + pages 40 to 95
        for p in range(0, min(15, len(reader.pages))):
            f.write(f"\n--- PAGE {p+1} (ÍNDICE) ---\n")
            f.write((reader.pages[p].extract_text() or "") + "\n")
            
        for p in range(40, min(95, len(reader.pages))):
            f.write(f"\n--- PAGE {p+1} ---\n")
            f.write((reader.pages[p].extract_text() or "") + "\n")

if __name__ == "__main__":
    extract_gargiulo_chapters()
    extract_martinez_chapters()
    print("Extracción de capítulos completada con éxito.")
