"""
find_duplicate_games.py
------------------------
Varre todos os CSVs de data/raw/ e identifica quaisquer game_pk que
aparecem em mais de um arquivo (indicando um jogo coletado duas vezes,
geralmente em datas adjacentes por causa de inconsistência entre o
parâmetro de data da query e o officialDate retornado pela API).

Uso:
    python scripts/find_duplicate_games.py
"""

import pandas as pd
from pathlib import Path
from collections import defaultdict

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"


def main():
    files = sorted(RAW_DIR.glob("*.csv"))
    print(f"Verificando {len(files)} arquivo(s)...\n")

    game_pk_to_files = defaultdict(set)

    for f in files:
        try:
            df = pd.read_csv(f, usecols=["game_pk"], low_memory=False)
        except Exception as e:
            print(f"  ⚠ Erro ao ler {f.name}: {e}")
            continue

        for gpk in df["game_pk"].dropna().unique():
            game_pk_to_files[int(gpk)].add(f.name)

    duplicated = {gpk: fs for gpk, fs in game_pk_to_files.items() if len(fs) > 1}

    if not duplicated:
        print("Nenhum game_pk duplicado entre arquivos encontrado.")
        return

    print(f"Encontrados {len(duplicated)} game_pk duplicado(s) entre arquivos:\n")
    for gpk, fs in sorted(duplicated.items()):
        print(f"  game_pk {gpk}: {sorted(fs)}")

    print(f"\nTotal de game_pk afetados: {len(duplicated)}")
    print("Total de arquivos envolvidos:", len(set().union(*duplicated.values())))


if __name__ == "__main__":
    main()
