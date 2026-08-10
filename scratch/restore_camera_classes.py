# -*- coding: utf-8 -*-
"""
Extrae los bloques de clases faltantes desde el commit faeee5e y los
agrega al final de modules/camera.py actual.
"""
import subprocess, os

# 1. Leer la versión con las clases completas (faeee5e)
old = subprocess.check_output(
    ['C:/Program Files/Git/cmd/git.exe', 'show', 'faeee5e:modules/camera.py'],
    text=True, encoding='utf-8'
).splitlines()

# 2. Encontrar los bloques de las 4 clases faltantes
class_starts = {}
for i, line in enumerate(old):
    for cls in ['class SetScaleDialog', 'class TrackpyDialog', 'class Backend', 'class Laser532Window', 'class Laser532Backend']:
        if line.startswith(cls):
            class_starts[cls.split()[1].split('(')[0]] = i

# Ordenar por línea de aparición
sorted_classes = sorted(class_starts.items(), key=lambda x: x[1])
print("Clases encontradas:", [(c, n) for c, n in sorted_classes])

# 3. Extraer bloques (de inicio de cada clase al inicio de la siguiente)
blocks = []
for idx, (cls_name, start_line) in enumerate(sorted_classes):
    if idx + 1 < len(sorted_classes):
        end_line = sorted_classes[idx + 1][1]
    else:
        end_line = len(old)
    block = '\n'.join(old[start_line:end_line])
    blocks.append((cls_name, block))
    print(f"  Extracted {cls_name}: lines {start_line+1}–{end_line} ({end_line-start_line} lines)")

# 4. Leer el camera.py actual
target = r'c:\Users\josel\Documents\Obsidian_Vault\printing3\modules\camera.py'
with open(target, 'r', encoding='utf-8') as f:
    current = f.read()

# 5. Verificar qué clases ya existen y cuáles faltan
missing = [(name, blk) for name, blk in blocks if f'class {name}' not in current]
print(f"\nClases faltantes en modules/camera.py: {[n for n,_ in missing]}")

# 6. Añadir sólo las que faltan al final
separator = '\n\n# ══════════════════════════════════════════════════════════════════════════════\n'
additions = separator.join(
    f'#  {name.upper()}\n# ══════════════════════════════════════════════════════════════════════════════\n\n' + blk
    for name, blk in missing
)

new_content = current.rstrip('\n') + '\n\n\n' + additions + '\n'

with open(target, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"\nActualizado modules/camera.py: {len(new_content.splitlines())} líneas totales.")
