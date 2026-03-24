import sys
import shutil
import subprocess
from pathlib import Path

# V prostředí Snakemake je globálně dostupný objekt `snakemake`.

def main():
    print("\n=== KROK 1: Převod vstupních dat na NIfTI ===")
    
    in_dir = Path(snakemake.input.in_dir)
    out_nii = Path(snakemake.output.nii)

    # Načtení výběru formátu vstupu
    user_settings = getattr(snakemake, 'config', {})
    input_format = user_settings.get("input_format", "auto").lower()
    print(f"Zvolený vstupní formát z konfigurace: {input_format}")

    # 1. Je na vstupu rovnou NIfTI?
    if input_format in ["auto", "nifti"]:
        nii_files = list(in_dir.rglob("*.nii.gz")) + list(in_dir.rglob("*.nii"))
        if nii_files:
            print(f"Nalezen NIfTI soubor: {nii_files[0]}")
            print("Kopíruji soubor na místo očekávaného výstupu a přeskakuji konverzi.")
            shutil.copy2(nii_files[0], out_nii)
            sys.exit(0)
        elif input_format == "nifti":
            print("[ERROR] Byl vynucen formát NIfTI, ale žádný takový soubor nebyl nalezen ve vstupní složce.")
            sys.exit(1)

    # 2. Jsou na vstupu RAW data?
    if input_format in ["auto", "raw"]:
        raw_files = list(in_dir.rglob("*.raw"))
        if raw_files:
            raw_file = raw_files[0]
            # Pokus o nalezení coordinates.txt buď hned ve složce s RAWem nebo kdekoliv
            coords_files = list(raw_file.parent.glob("coordinates.txt"))
            if not coords_files:
                coords_files = list(in_dir.rglob("coordinates.txt"))
            
            if not coords_files:
                print(f"[ERROR] Nebyl nalezen soubor coordinates.txt pro {raw_file}.")
                sys.exit(1)
                
            coords_file = coords_files[0]
            
            # Načtení případných parametrů z configu
            raw_params = user_settings.get('raw_parameters', {}).get(raw_file.name, {})
            dims = raw_params.get('dimensions', '512x512x120')
            
            script_path = str(Path("src/python/01_converting/1_raw_ct2nifti.py").resolve())
            print(f"Nalezen RAW soubor: {raw_file}.")
            print(f"Spouštím skript pro převod RAW na NIfTI (s rozměry {dims})...")
            
            cmd = [
                sys.executable, script_path, 
                str(raw_file), str(coords_file), 
                "-o", str(out_nii),
                "--shape", dims
            ]
            
            res = subprocess.run(cmd, check=False)
            if res.returncode != 0:
                print(f"[ERROR] Běh skriptu 1_raw_ct2nifti.py skončil s chybou {res.returncode}.")
                sys.exit(1)
            sys.exit(0)
        elif input_format == "raw":
            print("[ERROR] Byl vynucen formát RAW, ale žádný takový soubor nebyl nalezen.")
            sys.exit(1)

    # 3. Jsou na vstupu DICOMy?
    if input_format in ["auto", "dicom"]:
        # Kontrolujeme i rovnou kořenovou složku `in_dir`, nebo jakoukoliv podřízenou složku.
        directories_to_check = [in_dir] + [d for d in in_dir.iterdir() if d.is_dir()]
        for d in directories_to_check:
            has_dicom = False
            for f in d.iterdir():
                # DICOMy často končí .dcm nebo nemají žádnou příponu (přitom to nesmí být coordinates.txt)
                if f.is_file() and (f.suffix.lower() == '.dcm' or (f.suffix == '' and f.name.lower() != 'coordinates.txt')):
                    has_dicom = True
                    break
                    
            if has_dicom:
                script_path = str(Path("src/python/01_converting/1_dicom_ct2nifti.py").resolve())
                print(f"Nalezeny DICOM soubory ve složce: {d}.")
                print("Spouštím skript pro převod DICOM na NIfTI...")
                cmd = [sys.executable, script_path, str(d), "-o", str(out_nii)]
                res = subprocess.run(cmd, check=False)
                if res.returncode != 0:
                    print(f"[ERROR] Běh skriptu 1_dicom_ct2nifti.py skončil s chybou {res.returncode}.")
                    sys.exit(1)
                sys.exit(0)
        if input_format == "dicom":
            print("[ERROR] Byl vynucen formát DICOM, ale žádné takové soubory nebyly nalezeny.")
            sys.exit(1)
            
    print(f"[ERROR] Nebyly nalezeny žádné vstupní soubory podporované zvoleným formátem '{input_format}'.")
    print("Zkontrolujte prosím složku data/input nebo nastavte správný formát v konfiguraci.")
    sys.exit(1)

if __name__ == "__main__":
    main()
