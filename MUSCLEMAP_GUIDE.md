# MuscleMap Integration Guide

## Přehled

MSK-PIPE nyní zahrnuje integraci s **MuscleMap**, open-source nástrojem pro automatizovanou segmentaci svalů z CT/MRI snímků. Pipeline nyní umí:

✓ Automaticky stáhnout MuscleMap z GitHubu pokud chybí  
✓ Segmentovat svaly (Abductor Brevis, Gluteus Medius, Gluteus Maximus, Iliacus z pelvis regionu)  
✓ Vyčistit svalové masky  
✓ Konvertovat svalové masky do 3D OBJ modelů  
✓ Automaticky detekovat a používat GPU pokud je dostupné  

## Systémové požadavky

- **Python 3.11.8**
- **PyTorch** (s CUDA support pro GPU)
- **Git** (pro stažení MuscleMap repozitáře)
- **VTK >= 9.2** (pro mask2stl konverzi)

## Setup proces

### 1. Spustit runner.py (pre-flight checks)

```bash
python runner.py
```

Runner vám automaticky:
- Ověří existenci MuscleMap repozitáře
- Nabídne automatické klonování z GitHubu pokud chybí
- Vytvoří Micromamba prostředí `msk_musclemap` s PyTorch CUDA

### 2. Ověřit MuscleMap instalaci

Pokud chcete ručně ověřit MuscleMap:

```bash
# Aktivovat prostředí
conda activate msk_musclemap

# Otestovat mm_segment příkaz
mm_segment --help
```

Pokud se objeví chyba, MuscleMap potřebuje manuální instalaci:

```bash
cd src/MuscleMap
pip install -e .
# Pak nainstalovat PyTorch s CUDA support (viz README v MuscleMap repozitáři)
```

## Pipeline Workflow

Nový workflow zahrnuje tyto kroky:

```
Input CT/MRI (ct.nii.gz)
         ↓
    [load_image]
         ↓
  TotalSegmentator (kosti)          MuscleMap (svaly)
    [total_segmentator_raw]      [muscle_map_raw]
         ↓                              ↓
  [clean_masks]              [clean_muscle_masks]
         ↓                              ↓
  [cpp_mask2stl]             [cpp_muscle_mask2obj]
  (STL modely kostí)         (OBJ modely svalů)
         ↓                              ↓
  [merge_meshes] ←→ Bone meshes (STL)    Muscle meshes (OBJ)
         ↓
  [msk_staple] → bone_model.osim
```

## Konfigurace svalů

### Label čísla v MuscleMap

Soubor `src/python/02a_muscles_segm/2b_clean_muscle_masks.py` obsahuje definici svalů:

```python
MUSCLE_LABELS = {
    "abductor_brevis_l": 1,      # TODO: aktualizovat podle skutečného výstupu
    "abductor_brevis_r": 2,
    "gluteus_medius_l": 3,
    "gluteus_medius_r": 4,
    "gluteus_maximus_l": 5,
    "gluteus_maximus_r": 6,
    "iliacus_l": 7,
    "iliacus_r": 8,
}
```

**DŮLEŽITÉ**: Zjistěte správná label čísla z MuscleMap dokumentace nebo experimentováním. Label čísla se mohou lišit podle verze modelu!

### Parametry čištění

V `config.json` nebo `config/user_settings.yaml` nastavte:

```json
{
  "muscle_preproc": {
    "min_voxels": 100,
    "opening_kernel": 3,
    "closing_kernel": 3,
    "fill_holes": true,
    "keep_largest": true
  }
}
```

Parametry:
- `min_voxels`: Odstraní komponenty menší než N voxelů (výchozí: 100)
- `opening_kernel`: Morfologické otevření (odstraní malý šum)
- `closing_kernel`: Morfologické zavření (vyplní malé díry)
- `fill_holes`: Vyplní dutiny v segmentaci
- `keep_largest`: Ponechá pouze největší vázanou komponentu

## Spuštění pipeline

### Standardní spuštění (s kostmi i svaly)

```bash
snakemake --cores all --use-conda
```

Snakemake automaticky spustí všechna pravidla včetně MuscleMap.

### Spuštění pouze bez svalů (pokud MuscleMap není ve stroji)

Edituji v Snakefile `rule all` aby nezahrnoval `muscle_models`:

```python
rule all:
    input:
        os.path.join(TEMP_DIR, "output_STAPLE", "bone_model.osim"),
        # os.path.join(TEMP_DIR, "muscle_models"),  # Zakomentovat
```

## Výstupní soubory

Po spuštění budete mít:

```
data/temp/
├── muscle_segmentations/          ← Čištěné svalové masky (NIfTI)
│   ├── abductor_brevis_l.nii.gz
│   ├── gluteus_medius_l.nii.gz
│   ├── iliacus_l.nii.gz
│   └── ...
│
└── muscle_models/                 ← OBJ 3D modely
    ├── abductor_brevis_l.obj
    ├── gluteus_medius_l.obj
    ├── iliacus_l.obj
    └── ...
```

## Řešení problémů

### MuscleMap selže se chybou "mm_segment not found"

```bash
# Ověřit instalaci
conda activate msk_musclemap
python -c "import torch; print(torch.cuda.is_available())"

# Znovu instalovat z repozitáře
cd src/MuscleMap
pip install -e .
```

### Chybí label čísla pro svaly

Spusťte MuscleMap ručně a zkontrolujte výstup:

```bash
mm_segment -i ct.nii.gz
# Načtěte _dseg.nii.gz vImageJ/ITK-SNAPu a zjistěte label čísla
```

### OBJ modely nejsou vytvořeny

Zkontrolujte:
1. Je mask2stl zkompilován? Viz `compile_mask2stl()` v runner.py
2. Jsou svalové masky validní? Zkontrolujte v `muscle_segmentations/`

## GPU Podpora

MuscleMap automaticky detekuje NVIDIA GPU. Pokud máte RTX kartu s CUDA:

```bash
# Ověřit GPU support
python -c "import torch; print('GPU dostupné:', torch.cuda.is_available())"
```

Prostředí `msk_musclemap` se nainstaluje s PyTorch CUDA buildou.

## Reference

- **MuscleMap GitHub**: https://github.com/MuscleMap/MuscleMap
- **MuscleMap dokumentace**: Viz README v repozitáři
- **Muscle labels**: Běží na whole-body modelu (99+ svalů a kostí)

## Poznámky

- Prosím, citujte MuscleMap publikaci při používání: McKay et al., J Imaging. 2024;10(11):262
- Čištění masek se aplikuje **po** MuscleMap segmentaci (fill_holes, otevření/zavření, remove_small_objects)
- OBJ formát je preferován pro svaly (textový formát, lépe se manipuluje)
- STL formát se používá pro kosti (binární, menší soubory)
