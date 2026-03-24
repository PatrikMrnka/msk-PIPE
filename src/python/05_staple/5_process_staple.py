"""
Skript pro spuštění STAPLE workflow z Pythonu pomocí MATLAB Engine.

Co dělá:
- Spustí MATLAB Engine a nastaví vyhledávací cesty tak, aby MATLAB viděl knihovnu
    STAPLE (s podsložkami) a lokální skript `hip_model.m`.
- Volá skript `hip_model.m`, který vytvoří OpenSim model(y) a uloží je
    do složky `output_STAPLE` v aktuálním adresáři (`5_staple_study/output_STAPLE`).

Vstupy a výstupy:
- Vstupní STL geometrie se očekávají ve složce `5_staple_study/data/<dataset>/stl`,
    kde `<dataset>` (např. `test`) je nastaven uvnitř `hip_model.m`.
- Výstupy (OpenSim .osim, geometrie pro vizualizaci atd.) se ukládají do
    `5_staple_study/output_STAPLE` (stejný název používá i `hip_model.m`).

Požadavky:
- MATLAB s nainstalovaným MATLAB Engine for Python v aktivním Python prostředí
    (doporučeno: samostatné `.venv` přímo ve složce `5_staple_study`).
- Složka `STAPLE` (nebo její analog) musí být přítomná v `5_staple_study`.

Použití:
        python process_staple.py

Chování při chybách:
- Vypsání chybové hlášky a korektní ukončení MATLAB Engine v `finally` bloku.
"""

import sys
import importlib
try:
    matlab_engine = importlib.import_module('matlab.engine')
except Exception:
    print(
        "MATLAB Engine for Python není dostupný v aktuálním prostředí.\n"
        "Spusťte tento skript v .venv, kde je nainstalovaný MATLAB Engine\n"
        "(doporučeno: 5_staple_study/.venv).\n\n"
        "Instalace (příklad):\n"
        "- spusťte setup z <MATLAB>/extern/engines/python\n"
    )
    sys.exit(1)
from pathlib import Path

# --- 1. Cesty relativně k tomuto souboru ---
# Složka projektu `5_staple_study` (obsahuje `STAPLE` a `hip_model.m`).
project_folder = Path(__file__).resolve().parent

# Cesty ke klíčovým složkám
staple_folder_path = project_folder / 'STAPLE'  # případně 'msk-STAPLE/STAPLE'
script_folder_path = project_folder            # kde leží `hip_model.m`
script_name = 'hip_model'                      # název .m skriptu bez přípony

# --- 2. Spuštění MATLAB Engine ---
print("Spouštím MATLAB engine...")
eng = matlab_engine.start_matlab()

try:
    # --- 3. Přidání potřebných cest do MATLABu ---
    print(f"Přidávám do cesty: {staple_folder_path}")
    eng.addpath(eng.genpath(str(staple_folder_path)), nargout=0)
    
    print(f"Přidávám do cesty: {script_folder_path}")
    # přidej i aktuální skriptovací složku (kvůli `hip_model.m`)
    eng.addpath(str(script_folder_path), nargout=0)

    # --- 4. Spuštění skriptu ---
    print(f"Spouštím skript: {script_name}.m ...")
    eng.workspace['vstupni_cesta'] = 'bone_datasets'
    eng.workspace['vystupni_cesta'] = 'output_STAPLE'
    eng.eval(script_name, nargout=0)
    
    print("✅ Skript byl úspěšně dokončen.")

except Exception as e:
    print(f"❌ Došlo k chybě:\n{e}")

finally:
    eng.quit()
    print("MATLAB engine byl ukončen.")