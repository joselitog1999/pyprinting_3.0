import os
import sys
from pypdf import PdfReader

PDF_DIR = r"c:\Users\josel\Documents\Obsidian_Vault\printing3\docs\bibliografia"
OUTPUT_FILE = r"c:\Users\josel\Documents\Obsidian_Vault\printing3\scratch\theses_extracted_content.txt"

def extract_thesis_data():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for filename in ["Julian_Gargiulo_2017.pdf", "Tesis Luciana Martinez.pdf"]:
            path = os.path.join(PDF_DIR, filename)
            out.write("=" * 90 + "\n")
            out.write(f"DOCUMENTO: {filename}\n")
            out.write("=" * 90 + "\n\n")
            
            reader = PdfReader(path)
            total = len(reader.pages)
            out.write(f"Total de páginas: {total}\n\n")
            
            # 1. Outline
            try:
                out.write("--- ÍNDICE / ESTRUCTURA DE CAPÍTULOS ---\n")
                def dump_outline(elem, level=0):
                    if isinstance(elem, list):
                        for item in elem:
                            dump_outline(item, level)
                    else:
                        title = getattr(elem, "title", str(elem))
                        out.write("  " * level + f"* {title}\n")
                dump_outline(reader.outline)
                out.write("\n")
            except Exception as e:
                out.write(f"No outline: {e}\n\n")
                
            # 2. Search key terms and chapters
            key_terms = [
                "optical printing", "impresión óptica", "shutter", "obturador", 
                "scattering", "gradiente", "fuerza de radiación", "radiation force",
                "drift", "deriva", "APTES", "silanización", "potencial zeta",
                "criterio de parada", "stopping criterion", "step and glue",
                "confocal", "fotodiodo", "photodiode", "autofoco", "autofocus",
                "dimer", "dímero", "CTAB", "citrato", "gold", "oro", "silver", "plata",
                "laser 532", "laser 808", "laser 637", "laser 592", "heating", "calentamiento",
                "temperature", "temperatura", "cavitation", "nanocavitation"
            ]
            
            out.write("--- BÚSQUEDA DE SECCIONES CRÍTICAS POR PALABRAS CLAVE ---\n")
            term_hits = {term: [] for term in key_terms}
            
            for page_num in range(total):
                page_text = reader.pages[page_num].extract_text() or ""
                page_lower = page_text.lower()
                for term in key_terms:
                    if term in page_lower:
                        term_hits[term].append(page_num + 1)
                        
            for term, pages in term_hits.items():
                out.write(f"- '{term}': {len(pages)} menciones (Páginas: {pages[:15]}...)\n")
            out.write("\n" + "="*90 + "\n\n")

    print(f"Extracción inicial guardada en: {OUTPUT_FILE}")

if __name__ == "__main__":
    extract_thesis_data()
