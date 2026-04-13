import xml.etree.ElementTree as ET
import subprocess
import os
import sys
import difflib

# --- Konfigurace ---
XML_INPUT = 'data/setup_MuscleGeneratorTool.xml'
XML_OUTPUT = 'subject_specific_setup.xml'
CPP_EXECUTABLE = './build/Release/extract_attachments.exe'  # Uprav dle svého OS (např. 'AttachmentExtractor.exe' ve Windows)
DISTANCE_THRESHOLD = "0.5" # Maximální vzdálenost v mm pro určení úponu
MUSCLES_DIR = 'muscles' # Složka s tvými .obj modely svalů

# Slovník pro překlad názvů kostí z XML na reálné soubory na disku
BONE_FILE_MAPPING = {
    "pelvis": "pelvis_no_sacrum.obj",
    "femur_r": "femur_r.obj",
    "tibia_r": "tibia_r.obj"
}

def update_model_file(root, new_model_name="bone_model.osim"):
    """Aktualizuje hlavní model file v XML za subject-specific model."""
    tool = root.find('MuscleGeneratorTool')
    if tool is not None:
        model_file_elem = tool.find('model_file')
        if model_file_elem is not None:
            print(f"[*] Aktualizuji model_file: {model_file_elem.text} -> {new_model_name}")
            model_file_elem.text = new_model_name

def rename_and_map_muscles(root):
    """
    Najde svaly ve složce 'muscles', vybere ty pro pravou stranu (_r),
    najde nejpodobnější název podle XML, přejmenuje soubor a aktualizuje XML.
    """
    print("\n=== Fáze 1: Párování a přejmenování svalů ===")
    if not os.path.exists(MUSCLES_DIR):
        print(f"[!] CHYBA: Složka '{MUSCLES_DIR}' neexistuje. Vytvoř ji a vlož do ní .obj svaly.")
        sys.exit(1)

    # Získání všech souborů pro pravou stranu
    available_files = [f for f in os.listdir(MUSCLES_DIR) if f.endswith('.obj') and '_r' in f.lower()]
    
    # Vytvoření "očištěného" slovníku pro lepší porovnávání (odstraníme podtržítka a _r)
    clean_to_real = {}
    for f in available_files:
        clean_name = f.lower().replace('_r', '').replace('.obj', '').replace('_', '')
        clean_to_real[clean_name] = f

    for generator in root.findall('.//MuscleGenerator'):
        xml_name = generator.get('name')  # např. 'AdductorBrevis'
        clean_xml_name = xml_name.lower().replace('_', '')
        
        # Hledání nejlepší shody s minimální podobností 60 %
        matches = difflib.get_close_matches(clean_xml_name, clean_to_real.keys(), n=1, cutoff=0.6)
        
        mesh_elem = generator.find('.//Mesh/mesh_file')
        
        if matches:
            best_match_key = matches[0]
            old_filename = clean_to_real[best_match_key]
            old_filepath = os.path.join(MUSCLES_DIR, old_filename)
            
            # Nový čistý název podle XML
            new_filename = f"{xml_name}.obj"
            new_filepath = os.path.join(MUSCLES_DIR, new_filename)
            
            # Fyzické přejmenování na disku
            if old_filename != new_filename and os.path.exists(old_filepath):
                os.rename(old_filepath, new_filepath)
                print(f"  [+] Přejmenováno: {old_filename} -> {new_filename}")
                del clean_to_real[best_match_key] # Odebereme ze seznamu, abychom ho nepoužili dvakrát
            
            # Aktualizace cesty v XML
            if mesh_elem is not None:
                mesh_elem.text = new_filepath
                
        else:
            # Kontrola, zda už soubor nebyl přejmenován při předchozím spuštění skriptu
            expected_filepath = os.path.join(MUSCLES_DIR, f"{xml_name}.obj")
            if os.path.exists(expected_filepath):
                if mesh_elem is not None:
                    mesh_elem.text = expected_filepath
                print(f"  [i] Sval {xml_name}.obj již existuje, pouze aktualizuji XML.")
            else:
                print(f"  [!] UPOZORNĚNÍ: Nenalezen žádný vhodný _r soubor pro sval '{xml_name}'")

def run_cpp_extractor(bone_obj, muscle_obj, threshold, output_vtk):
    """Sestaví a spustí C++ program jako podproces."""
    if not os.path.exists(bone_obj):
        print(f"[!] CHYBA: Chybí kost {bone_obj}. Přeskakuji.")
        return
    if not os.path.exists(muscle_obj):
        print(f"[!] CHYBA: Chybí sval {muscle_obj}. Přeskakuji.")
        return

    cmd = [CPP_EXECUTABLE, bone_obj, muscle_obj, str(threshold), output_vtk]
    print(f"    -> Spouštím C++ extrakci úponu do: {output_vtk}")
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] CHYBA při běhu C++ programu:")
        print(e.stderr)
    except FileNotFoundError:
        print(f"[!] CHYBA: C++ program '{CPP_EXECUTABLE}' nenalezen. Je zkompilovaný?")
        sys.exit(1)

def process_muscle_generators(root):
    """Projde všechny svaly v XML a zavolá pro ně extrakci úponů."""
    print("\n=== Fáze 2: Výpočet úponových oblastí (Origin & Insertion) ===")
    for generator in root.findall('.//MuscleGenerator'):
        muscle_name = generator.get('name')
        
        # Získání správné cesty ke svalu (ta už byla upravena ve Fázi 1)
        mesh_file_elem = generator.find('.//Mesh/mesh_file')
        if mesh_file_elem is None:
            continue
        muscle_obj = mesh_file_elem.text

        # Zpracování origin a insertion
        for attachment in generator.findall('.//AttachmentArea'):
            att_type_elem = attachment.find('type')
            body_elem = attachment.find('body')
            point_file_elem = attachment.find('point_file')
            
            if att_type_elem is None or body_elem is None or point_file_elem is None:
                continue
                
            att_type = att_type_elem.text
            bone_xml_name = body_elem.text
            output_vtk = point_file_elem.text
            
            # Zajištění, že se VTK uloží např. do složky muscles nebo examples (zde do kořene)
            # Pokud chceš výstupy jinam, můžeš k output_vtk přidat cestu
            
            bone_obj = BONE_FILE_MAPPING.get(bone_xml_name, f"{bone_xml_name}.obj")
            
            print(f"  * {muscle_name} [{att_type.upper()}] -> Kost: {bone_obj}")
            run_cpp_extractor(bone_obj, muscle_obj, DISTANCE_THRESHOLD, output_vtk)

def main():
    print("=== Start Pipeline ===")
    
    if not os.path.exists(XML_INPUT):
        print(f"[!] CHYBA: Vstupní soubor {XML_INPUT} nenalezen.")
        return
        
    tree = ET.parse(XML_INPUT)
    root = tree.getroot()

    # 1. Aktualizace hlavního modelu
    update_model_file(root, new_model_name="bone_model.osim")

    # 2. Přejmenování souborů svalů a aktualizace XML (<mesh_file>)
    rename_and_map_muscles(root)

    # 3. Spuštění výpočtu úponů
    process_muscle_generators(root)

    # 4. Uložení výsledného XML
    tree.write(XML_OUTPUT, encoding='utf-8', xml_declaration=True)
    print(f"\n=== Hotovo. Nový setup připraven jako: {XML_OUTPUT} ===")

if __name__ == "__main__":
    main()