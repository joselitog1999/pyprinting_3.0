import os

OUTPUT_DIR = r"c:\Users\josel\Documents\Obsidian_Vault\printing3\scratch"

def summarize_theses():
    with open(os.path.join(OUTPUT_DIR, "theses_deep_synthesis.txt"), "w", encoding="utf-8") as out:
        # 1. Gargiulo Chapter 3 & 4
        with open(os.path.join(OUTPUT_DIR, "gargiulo_ch3_ch4_ch5.txt"), "r", encoding="utf-8") as f:
            content = f.read()
            out.write("=== JULIAN GARGIULO 2017: CONCEPTOS Y MODELOS CLAVE ===\n")
            # Extract key sections
            for kw in ["3.1", "3.2", "4.1", "4.2", "4.3", "5.1", "5.2", "6.1"]:
                pos = content.find(kw)
                if pos != -1:
                    snippet = content[pos:pos+1500]
                    out.write(f"\n--- SECCIÓN {kw} ---\n{snippet}\n" + "-"*50 + "\n")

        # 2. Martinez Setup & Physics
        with open(os.path.join(OUTPUT_DIR, "martinez_chapters.txt"), "r", encoding="utf-8") as f:
            content = f.read()
            out.write("\n=== LUCIANA MARTINEZ: CONCEPTOS Y MODELOS CLAVE ===\n")
            for kw in ["ÍNDICE", "Capítulo 2", "Capítulo 3", "Capítulo 4", "Capítulo 5", "obturador", "fotodiodo", "APTES", "deriva", "dímeros"]:
                pos = 0
                count = 0
                while count < 3:
                    pos = content.lower().find(kw.lower(), pos)
                    if pos == -1:
                        break
                    snippet = content[pos:pos+1000]
                    out.write(f"\n--- HIT '{kw}' (#{count+1}) ---\n{snippet}\n" + "-"*50 + "\n")
                    pos += 1000
                    count += 1

    print("Síntesis profunda generada en theses_deep_synthesis.txt")

if __name__ == "__main__":
    summarize_theses()
