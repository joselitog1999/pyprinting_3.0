import os
import sys
from pypdf import PdfReader

PDF_DIR = r"c:\Users\josel\Documents\Obsidian_Vault\printing3\docs\bibliografia"

def analyze_pdf(filename):
    path = os.path.join(PDF_DIR, filename)
    print("=" * 80)
    print(f"ANALIZANDO TESIS: {filename}")
    print("=" * 80)
    reader = PdfReader(path)
    total_pages = len(reader.pages)
    print(f"Total de páginas: {total_pages}")
    
    # Extract outline / bookmarks if available
    try:
        outline = reader.outline
        print(f"\n--- ESTRUCTURA / OUTLINE ({filename}) ---")
        def print_outline(elem, indent=0):
            if isinstance(elem, list):
                for item in elem:
                    print_outline(item, indent)
            else:
                title = getattr(elem, "title", str(elem))
                page = getattr(elem, "page", None)
                print("  " * indent + f"- {title}")
        print_outline(outline)
    except Exception as e:
        print(f"No se pudo extraer outline automático: {e}")
        
    # Search for first 15 pages to find title, abstract, table of contents
    print("\n--- PRIMERAS 12 PÁGINAS (ÍNDICE / RESUMEN) ---")
    for i in range(min(12, total_pages)):
        text = reader.pages[i].extract_text()
        if text:
            first_lines = "\n".join([line.strip() for line in text.split("\n") if line.strip()][:15])
            print(f"[Página {i+1}]:\n{first_lines}\n" + "-"*40)

if __name__ == "__main__":
    analyze_pdf("Julian_Gargiulo_2017.pdf")
    print("\n" * 2)
    analyze_pdf("Tesis Luciana Martinez.pdf")
