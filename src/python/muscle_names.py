"""
muscle_names.py -- Shared mapping between CamelCase muscle names and file-system stems.

Used by:
  - run_extraction.py     (to find .obj files for each topology entry)
  - generate_attachment_xml.py  (to find .obj files for the XML builder)

The CamelCase keys match the names in config/muscle_topology.json.
The snake_case values match the file stems produced by extract_muscle_masks.py.
"""

MUSCLE_NAME_TO_STEM: dict[str, str] = {
    "Iliacus": "iliacus",
    "GluteusMaximus": "gluteus_maximus",
    "GluteusMedius": "gluteus_medius",
    "GluteusMinimus": "gluteus_minimus",
    "Piriformis": "piriformis",
    "BicepsFemoris": "biceps_femoris",
    "Pectineus": "pectineus",
    "AdductorMagnus": "adductor_magnus",
    "AdductorBrevis": "adductor_brevis",
    "RectusFemoris": "rectus_femoris",
    "Psoas": "psoas_major",
    "Sartorius": "sartorius",
    "TensorFasciaLatae": "tensor_fasciae_latae",
    "Gracilis": "gracilis",
    "Semitendinosus": "semitendinosus",
    "Semimembranosus": "semimembranosus",
    "AdductorLongus": "adductor_longus",
}
