import argparse
import numpy as np
import nibabel as nib
import sys
import pathlib
from textwrap import dedent

def load_z_coordinates(path):
    """Načte Z souřadnice z textového souboru.

    Očekává jeden číselný údaj na řádek (mm). Podporuje desetinné čárky i tečky
    a volitelný sufix jednotky (např. "123,45", "123.45 mm"). Prázdné řádky
    jsou ignorovány. Pořadí hodnot zůstává zachováno (neprovádí se třídění).

    Parametry:
        path (str | pathlib.Path): Cesta k textovému souboru se souřadnicemi Z.

    Návratová hodnota:
        numpy.ndarray: 1D pole typu float64 tvaru (Z,), kde Z je počet řezů.

    Výjimky:
        ValueError: Pokud řádek nelze převést na číslo.
        OSError: Pokud se soubor nepodaří otevřít/načíst.
    """
    zs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # podporuje "123.45", "123,45", případně "123.45 mm"
            line = line.replace(",", ".").split()[0]
            zs.append(float(line))
    return np.asarray(zs, dtype=np.float64)

def check_uniform(zs, tol=1e-3):
    """Zhodnotí rovnoměrnost rozestupů vektoru Z-souřadnic.

    Spočítá rozdíly mezi sousedními prvky, odhadne průměrný krok dz a
    zkontroluje maximální odchylku od tohoto průměru. Pokud je odchylka
    větší než tolerance, považuje se mříž za nerovnoměrnou.

    Parametry:
        zs (array-like): 1D sekvence Z souřadnic (mm), délky Z.
        tol (float): Tolerance pro detekci nerovnoměrnosti (mm). Default: 1e-3.

    Návratová hodnota:
        tuple:
            - dz (float): Průměrný krok mezi řezy (mm).
            - nonuniform (bool): True, pokud je nerovnoměrnost > tol.
            - diffs (numpy.ndarray): 1D pole rozdílů sousedních Z.
    """
    diffs = np.diff(zs)
    dz = float(np.mean(diffs))
    nonuniform = np.max(np.abs(diffs - dz)) > tol
    return dz, nonuniform, diffs

def resample_to_uniform(grid, zs, target_dz):
    """Převzorkuje objem s nerovnoměrnými řezy na rovnoměrnou Z-mřížku.

    Použije lineární interpolaci (SciPy RegularGridInterpolator) z původních
    fyzikálních souřadnic (z_mm, y_idx, x_idx) na novou sadu rovnoměrných Z
    s krokem ``target_dz``.

    Parametry:
        grid (numpy.ndarray): 3D pole tvaru (Z, Y, X) s původními daty.
        zs (array-like): 1D pole délky Z s fyzickými Z souřadnicemi (mm).
        target_dz (float): Požadovaný krok v mm pro novou pravidelnou mříž.

    Návratová hodnota:
        tuple:
            - out (numpy.ndarray): Převzorkovaný objem tvaru (Z_new, Y, X) typu float32.
            - new_zs (numpy.ndarray): 1D pole nových Z souřadnic (mm) délky Z_new.

    Výjimky:
        ImportError: Pokud není dostupná knihovna SciPy.
        ValueError: Pokud vstupy nesplňují očekávané tvary/rozměry.
    """
    try:
        from scipy.interpolate import RegularGridInterpolator
    except Exception as e:
        print(
            "Nerovnoměrné Z rozestupy a chybí SciPy pro převzorkování.\n"
            "Buď nainstalujte SciPy (`pip install scipy`), nebo použijte parametr --allow-nonuniform "
            "a uložím NIfTI s průměrným dz.",
            file=sys.stderr,
        )
        raise

    # grid shape: (Z, Y, X). Vytvoříme pravidelnou mříž v Z s target_dz.
    z0, zN = zs[0], zs[-1]
    new_zs = np.arange(z0, zN + 0.5 * target_dz, target_dz, dtype=np.float64)
    Z, Y, X = grid.shape
    y_coords = np.arange(Y, dtype=np.float64)
    x_coords = np.arange(X, dtype=np.float64)

    # Interpolátor ve fyz. souřadnicích: (z_mm, y_idx, x_idx)
    interp = RegularGridInterpolator(
        (zs, y_coords, x_coords),
        grid.astype(np.float32),  # interpolace ve float
        method="linear",
        bounds_error=False,
        fill_value=0,
    )

    # Připravíme mříž bodů k vyhodnocení
    yy, xx = np.meshgrid(y_coords, x_coords, indexing="ij")
    # Bude to po řezech kvůli paměti
    out = np.zeros((len(new_zs), Y, X), dtype=np.float32)
    for i, z in enumerate(new_zs):
        pts = np.stack([np.full_like(yy, z, dtype=np.float64), yy, xx], axis=-1)
        out[i] = interp(pts)

    return out, new_zs

def main():
    """Hlavní vstupní bod CLI pro převod RAW CT na NIfTI s využitím Z souřadnic.

    Při nerovnoměrných rozestupech Z lze použít:
      - ``--allow-nonuniform``: uloží s průměrným dz (může vést k malé chybě),
      - ``--resample-dz <mm>``: převzorkuje na rovnoměrnou mříž (vyžaduje SciPy).

    Ukázka volání:
        python 1_raw_ct2nifti.py ./data/ct.raw ./data/coordinates.txt -o ./result/ct.nii.gz

    Exit kódy:
        0  při úspěchu,
        >0 při chybě vstupů, nekompatibilních rozměrech nebo I/O chybách.
    """
    ap = argparse.ArgumentParser(
        description="Převod RAW CT objemu na NIfTI s použitím Z souřadnic."
    )
    ap.add_argument("raw_path", type=pathlib.Path, help="Cesta k .raw souboru (např. LowerLimbCT_Single_381x245x1120.raw)")
    ap.add_argument("z_txt", type=pathlib.Path, help="Cesta k Z_coordinates_LowerLimbCT.txt")
    ap.add_argument("-o", "--out", type=pathlib.Path, default=None, help="Výstupní NIfTI (např. out.nii.gz)")
    ap.add_argument("--shape", type=str, default="381x245x1120",
                    help="Rozměry jako XxYxZ (default: 381x245x1120)")
    ap.add_argument("--dtype", type=str, default="int16",
                    help="Datový typ RAW (např. int16, uint16, float32). Default: int16")
    ap.add_argument("--little-endian", action="store_true", default=True,
                    help="RAW v little-endian (default: zapnuto)")
    ap.add_argument("--big-endian", action="store_true",
                    help="Přepne na big-endian (přepíše little-endian)")
    ap.add_argument("--xy-spacing", type=str, default="1.0,1.0",
                    help="Pixel spacing v rovině X,Y v mm jako 'sx,sy' (default: 1.0,1.0)")
    ap.add_argument("--origin-xy", type=str, default="0.0,0.0",
                    help="Počátek (mm) v X,Y jako 'ox,oy' (default: 0.0,0.0)")
    ap.add_argument("--allow-nonuniform", action="store_true",
                    help="Povolí uložení s průměrným dz i při nerovnoměrném Z (NIfTI neumí nerovnoměrné řezy).")
    ap.add_argument("--resample-dz", type=float, default=None,
                    help="Pokud Z nejsou uniformní, převzorkuje na daný dz (mm). Vyžaduje scipy.")
    ap.add_argument("--transpose", type=str, default="ZYX->XYZ",
                    choices=["none", "ZYX->XYZ"],
                    help="Jak přeuspořádat osy po načtení (RAW se typicky reshape(Z,Y,X), pak transponujeme na (X,Y,Z) pro NIfTI).")
    args = ap.parse_args()

    # Rozměry
    try:
        X, Y, Z = [int(v) for v in args.shape.lower().replace(" ", "").split("x")]
    except Exception:
        ap.error("Parametr --shape musí být ve formátu XxYxZ, např. 381x245x1120.")

    # Dtype s endianness
    base_dtype = np.dtype(args.dtype)
    if args.big_endian:
        dtype = base_dtype.newbyteorder(">")
    else:
        dtype = base_dtype.newbyteorder("<")

    # Načtení RAW
    nvox = X * Y * Z
    raw = np.fromfile(args.raw_path, dtype=dtype, count=nvox)
    if raw.size != nvox:
        sys.exit(f"ERROR: Očekáváno {nvox} voxelů, ale načteno {raw.size}. Zkontrolujte --shape, --dtype a endianitu.")

    vol_ZYX = raw.reshape((Z, Y, X))

    # Načtení Z souřadnic
    zs = load_z_coordinates(args.z_txt)
    if zs.size != Z:
        sys.exit(f"ERROR: Počet Z souřadnic ({zs.size}) neodpovídá počtu řezů Z ({Z}).")

    # Kontrola uniformity
    dz_mean, nonuniform, diffs = check_uniform(zs)
    print(f"Info: průměrný dz = {dz_mean:.6f} mm; max odchylka dz = {np.max(np.abs(diffs - dz_mean)):.6f} mm")

    # Případné převzorkování
    used_zs = zs
    used_grid = vol_ZYX
    if nonuniform:
        if args.resample_dz is not None:
            print(f"Z nejsou uniformní -> převzorkuji na dz = {args.resample_dz} mm (vyžaduje SciPy).")
            used_grid, used_zs = resample_to_uniform(vol_ZYX, zs, args.resample_dz)
        elif args.allow_nonuniform:
            print("Z nejsou uniformní -> uložím s průměrným dz (může způsobit drobnou chybu v pozici).")
        else:
            sys.exit(
                dedent(
                    """\
                    ERROR: Z souřadnice nejsou rovnoměrně rozestoupené.
                    Možnosti:
                      * přidejte --allow-nonuniform (uloží se s průměrným dz),
                      * nebo použijte --resample-dz <mm> pro převzorkování (vyžaduje SciPy).
                    """
                )
            )

    # Převod os dle volby
    if args.transpose == "ZYX->XYZ":
        data_xyz = np.transpose(used_grid, (2, 1, 0))  # (X, Y, Z)
    else:
        data_xyz = used_grid  # ponecháme (Z, Y, X) – nedoporučeno pro NIfTI

    # Spacing a počátek
    try:
        sx, sy = [float(v) for v in args.xy_spacing.replace(" ", "").split(",")]
        ox, oy = [float(v) for v in args.origin_xy.replace(" ", "").split(",")]
    except Exception:
        ap.error("Parametry --xy-spacing a --origin-xy musí být ve formátu 'a,b'.")

    # Pro Z použijeme z0 a dz_mean (nebo novou mřížku po resamplingu)
    z0 = float(used_zs[0])
    if used_zs.size > 1:
        dz_for_affine = float(np.mean(np.diff(used_zs)))
    else:
        dz_for_affine = float(dz_mean)

    # Afinní matice v RAS:
    # předpoklad: osy data_xyz jsou (X, Y, Z) a rostou doprava, dopředu, nahoru.
    # posunutí, rotace, změna měřítka a zkosení
    affine = np.array([
        [ sx, 0.0, 0.0, ox ],
        [ 0.0, sy, 0.0, oy ],
        [ 0.0, 0.0, dz_for_affine, z0 ],
        [ 0.0, 0.0, 0.0, 1.0 ]
    ], dtype=np.float64)

    # NIfTI obraz
    img = nib.Nifti1Image(data_xyz, affine)

    # Metadata
    hdr = img.header
    hdr.set_xyzt_units("mm")
    zooms = (sx, sy, dz_for_affine)
    try:
        hdr.set_zooms(zooms + (1.0,))
    except Exception:
        hdr.set_zooms(zooms)

    # Výstupní název
    out_path = args.out
    if out_path is None:
        out_path = args.raw_path.with_suffix("").with_suffix(".nii.gz")
    out_path = pathlib.Path(out_path)

    nib.save(img, out_path)
    print(f"Hotovo: {out_path}")

if __name__ == "__main__":
    main()