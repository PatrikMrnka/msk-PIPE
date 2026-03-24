import subprocess
import sys
from pathlib import Path
import shutil
import os
from datetime import datetime


def run(cmd, cwd=None, env=None, title=None):
	if title:
		print(f"\n=== {title} ===")
	print("CMD:", " ".join(map(str, cmd)))
	try:
		proc = subprocess.run(
			cmd,
			cwd=cwd,
			env=env,
			check=True,
		)
		return proc.returncode
	except subprocess.CalledProcessError as e:
		print(f"ERROR: Command failed with exit code {e.returncode}")
		raise



def copy_tree(src: Path, dst: Path, patterns=None, clear_dst=False):
	if clear_dst and dst.exists():
		shutil.rmtree(dst, ignore_errors=True)
	dst.mkdir(parents=True, exist_ok=True)

	if not src.exists():
		print(f"WARN: Zdrojová složka nenalezena: {src}")
		return

	if patterns is None:
		# plné zrcadlení (jen soubory; složky vytvoř dle potřeby)
		for root, dirs, files in os.walk(src):
			rel = Path(root).relative_to(src)
			(dst / rel).mkdir(parents=True, exist_ok=True)
			for f in files:
				s = Path(root) / f
				d = dst / rel / f
				shutil.copy2(s, d)
	else:
		# kopíruj pouze soubory odpovídající zadaným vzorům v libovolné hloubce
		for pattern in patterns:
			for s in src.rglob(pattern):
				if s.is_dir():
					continue
				rel = s.relative_to(src)
				d = dst / rel
				d.parent.mkdir(parents=True, exist_ok=True)
				shutil.copy2(s, d)


def main():
	"""Spustí celý pipeline běh od RAW po STAPLE výstupy pro nový run_id.

	Kroky:
	1) RAW -> NIfTI (ověření vstupů, uložení ct.nii.gz do ./result/<run_id>)
	2) Segmentace + předzpracování masek (TotalSegmentator)
	3) Konverze masek na STL (externí tsmask2stl.exe)
	4) Postprocessing sítí (slučování/dělení) do ./result/<run_id>/meshes_processed
	5) Přenos sítí do STAPLE, spuštění STAPLE a přesun výstupů zpět do ./result/<run_id>/output_STAPLE
	"""
	root = Path(__file__).resolve().parent

	# Připrav adresář běhu pod ./result jako YYYYMMDD_HHMMSS
	result_root = root / "result"
	
	run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
	run_base = result_root / run_id
	run_base.mkdir(parents=True, exist_ok=True)

	# Vstupy
	raw_path = root / "data" / "ct" / "ct.raw"
	coords_path = root / "data" / "ct" / "coordinates.txt"
	out_nii = run_base / "ct.nii.gz"

	# Krok 1: RAW -> NIfTI
	if not raw_path.exists():
		print(f"ERROR: Missing input RAW file: {raw_path}")
		sys.exit(1)
	if not coords_path.exists():
		print(f"ERROR: Missing coordinates file: {coords_path}")
		sys.exit(1)

	run(
		[sys.executable, str(root / "1_raw_ct2nifti.py"), str(raw_path), str(coords_path), "-o", str(out_nii)],
		title="1) RAW -> NIfTI",
	)

	# Krok 2: TotalSegmentator + předzpracování (do původní složky)
	run(
		[
			sys.executable,
			str(root / "2_nii2mask_preproc.py"),	
			str(out_nii),
			"--model",
			"ct",
			"--device",
			"gpu",
			"--keep-largest",
			"--min-voxels",
			"20000",
			"--opening",
			"2",
			"--closing",
			"2",
			"--fill-holes",
			"--inplace",
		],
		title="2) Segmentace + předzpracování masek",
	)

	# Práce s cestami pod vybraným adresářem běhu
	seg_dir = run_base / "segmentations"
	models_run = run_base / "models"

	# Krok 3: Konverze masek -> STL modely pomocí externího .exe
	exe = root / "3_mask2stl" / "win" / "tsmask2stl.exe"
	if not exe.exists():
		print(
			f"ERROR: Konvertor nenalezen: {exe}\n"
			f"Očekáváno v ./3_mask2stl/win/tsmask2stl.exe"
		)
		sys.exit(1)
	seg_dir.mkdir(parents=True, exist_ok=True)
	models_run.mkdir(parents=True, exist_ok=True)
	run(
		[str(exe), str(seg_dir), str(models_run), "--smooth", "50", "--relax", "0.2", "--decimate", "0.1"],
		title="3) Masky -> STL modely",
	)

	# Krok 4: Postprocessing/Sloučení sítí pro tento běh
	run([sys.executable, str(root / "4_mesh.py"), "--run-id", run_id], title="4) Postprocessing sítí")

	# Sítě již 4_mesh.py ukládá do běhové složky
	meshes_run = run_base / "meshes_processed"
	if not meshes_run.exists():
		print(f"WARN: Očekávané sítě na {meshes_run} nenalezeny.")

	# Krok 5a: Zkopíruj sítě do vstupu STAPLE
	staple_dir = root / "5_staple_study"
	staple_in = staple_dir / "data" / "test" / "stl"
	print(f"\n-- Kopíruji sítě do vstupu STAPLE: {staple_in}")
	copy_tree(meshes_run, staple_in, clear_dst=True)

	# Krok 5b: Spusť process_staple.py ve vlastním .venv
	staple_python = staple_dir / ".venv" / "Scripts" / "python.exe"
	if not staple_python.exists():
		print(
			f"WARN: STAPLE venv Python nenalezen na {staple_python}.\n"
			f"      Použiji aktuální interpreter: {sys.executable}"
		)
		staple_python = Path(sys.executable)

	process_script = staple_dir / "process_staple.py"
	if not process_script.exists():
		print(f"ERROR: Chybí spouštěcí skript STAPLE: {process_script}")
		sys.exit(1)

	# Pracovní adresář nastav na složku STAPLE, aby seděly relativní cesty uvnitř skriptu
	run(
		[str(staple_python), "-u", str(process_script)],
		cwd=str(staple_dir),
		title="5) Spuštění STAPLE (process_staple.py ve vlastním .venv)",
	)

	# Krok 5c: Zkopíruj vygenerované výstupy STAPLE do složky tohoto běhu
	staple_out_src = staple_dir / "output_STAPLE"
	staple_out_dst = run_base / "output_STAPLE"
	print(f"\n-- Přesouvám výstupy STAPLE: {staple_out_src} -> {staple_out_dst}")
	copy_tree(staple_out_src, staple_out_dst, clear_dst=True)

	print("\nVšechny kroky úspěšně dokončeny.")


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		print("Interrupted by user.")
		sys.exit(130)
	except Exception as e:
		# Already reported in run(); just exit non-zero
		sys.exit(1)

