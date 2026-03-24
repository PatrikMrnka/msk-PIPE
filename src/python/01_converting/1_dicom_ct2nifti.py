import argparse
import sys
import pathlib
import SimpleITK as sitk

def main():
    """Hlavní vstupní bod CLI pro převod DICOM série na NIfTI.

    Skript prohledá zadanou složku na přítomnost DICOM souborů, identifikuje
    jednotlivé série a převede zvolenou sérii (standardně tu první) do formátu
    NIfTI (.nii.gz). SimpleITK automaticky řeší prostorovou transformaci 
    (rozestupy pixelů, tloušťku řezu, počátek a orientaci).

    Ukázka volání:
        python 2_dicom2nifti.py ./data/dicom_folder -o ./result/ct.nii.gz

    Exit kódy:
        0  při úspěchu,
        >0 při chybě vstupů nebo chybějících datech.
    """
    ap = argparse.ArgumentParser(
        description="Převod složky s DICOM daty na objem NIfTI (.nii.gz)."
    )
    ap.add_argument("dicom_dir", type=pathlib.Path, 
                    help="Cesta ke složce obsahující DICOM soubory dané série.")
    ap.add_argument("-o", "--out", type=pathlib.Path, default=None, 
                    help="Výstupní NIfTI (např. vložte result.nii.gz). Defaultně se uloží do složky s DICOM daty.")
    ap.add_argument("--series-id", type=str, default=None,
                    help="Specifické ID série k převodu (pokud je ve složce smícháno více sérií).")
    
    args = ap.parse_args()

    dicom_dir_str = str(args.dicom_dir)

    if not args.dicom_dir.is_dir():
        sys.exit(f"ERROR: Zadaná cesta '{args.dicom_dir}' neexistuje nebo není složka.")

    # Inicializace čtečky DICOM sérií
    print(f"Prohledávám složku: {dicom_dir_str} ...")
    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(dicom_dir_str)

    if not series_ids:
        sys.exit("ERROR: Ve složce nebyly nalezeny žádné platné DICOM série.")

    # Výběr série
    if args.series_id:
        if args.series_id not in series_ids:
            print("Dostupné série ve složce:")
            for s_id in series_ids:
                print(f"  - {s_id}")
            sys.exit(f"ERROR: Série s ID '{args.series_id}' nebyla nalezena.")
        selected_series = args.series_id
    else:
        selected_series = series_ids
        if len(series_ids) > 1:
            print(f"UPOZORNĚNÍ: Nalezeno více sérií ({len(series_ids)}).")
            print("Dostupné série:")
            for s_id in series_ids:
                print(f"  - {s_id}")
            print(f"\nAutomaticky vybírám první nalezenou sérii: {selected_series}")
            print("Pokud chcete jinou, použijte parametr --series-id.\n")

    # Získání seznamu souborů patřících do vybrané série
    dicom_names = reader.GetGDCMSeriesFileNames(dicom_dir_str, selected_series)
    reader.SetFileNames(dicom_names)

    # Načtení obrazu do paměti
    print(f"Načítám {len(dicom_names)} DICOM souborů...")
    try:
        image = reader.Execute()
    except Exception as e:
        sys.exit(f"ERROR: Selhalo načítání DICOM dat. Detaily: {e}")

    # Výpis informací o načteném objemu
    size = image.GetSize()
    spacing = image.GetSpacing()
    print(f"Info: Načteno úspěšně.")
    print(f"  - Rozměry (X, Y, Z): {size} x {size} x {size}")
    print(f"  - Rozestupy (mm):    {spacing:.4f} x {spacing:.4f} x {spacing:.4f}")

    # Cesta pro uložení
    out_path = args.out
    if out_path is None:
        out_path = args.dicom_dir.parent / f"{args.dicom_dir.name}_converted.nii.gz"
    
    # SimpleITK potřebuje cesty jako stringy, nikoliv pathlib objekty (u některých verzí)
    out_path_str = str(out_path)

    # Uložení do NIfTI
    print(f"Ukládám do NIfTI...")
    try:
        sitk.WriteImage(image, out_path_str)
        print(f"Hotovo: {out_path_str}")
    except Exception as e:
        sys.exit(f"ERROR: Selhalo uložení souboru NIfTI. Detaily: {e}")

if __name__ == "__main__":
    main()