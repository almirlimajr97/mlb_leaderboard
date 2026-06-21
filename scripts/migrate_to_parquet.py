"""
migrate_to_parquet.py
-----------------------
Script de migração ÚNICA (rodar uma vez só): converte todos os CSVs
existentes em data/raw/ e os agregados data/df_batters_<season>.csv /
data/df_pitchers_<season>.csv para Parquet, e apaga os .csv originais
após confirmar que a conversão deu certo.

Uso:
    python scripts/migrate_to_parquet.py            # mostra o que faria (dry-run)
    python scripts/migrate_to_parquet.py --apply     # converte de fato e apaga os .csv
"""

import argparse
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"


def migrate_file(csv_path: Path, apply: bool) -> bool:
    """Converte um único CSV para Parquet, valida e (se --apply) apaga o CSV."""
    parquet_path = csv_path.with_suffix(".parquet")

    if parquet_path.exists():
        print(f"  ⏭  {parquet_path.name} já existe, pulando.")
        return False

    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except Exception as e:
        print(f"  ⚠ Erro ao ler {csv_path.name}: {e}")
        return False

    if not apply:
        print(f"  [dry-run] {csv_path.name} -> {parquet_path.name} ({len(df)} linhas)")
        return True

    df.to_parquet(parquet_path, index=False)

    # Valida: relê o parquet e confirma que bate em linhas e colunas
    df_check = pd.read_parquet(parquet_path)
    if len(df_check) != len(df) or list(df_check.columns) != list(df.columns):
        print(f"  ⚠ Validação falhou para {csv_path.name}! Parquet NÃO foi confiável, mantendo o CSV.")
        parquet_path.unlink(missing_ok=True)
        return False

    csv_path.unlink()
    print(f"  ✓ {csv_path.name} -> {parquet_path.name} ({len(df)} linhas, validado e CSV removido)")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplica a migração de fato (sem isso, só mostra o que faria)")
    args = parser.parse_args()

    print("=== Migrando data/raw/*.csv ===")
    raw_csvs = sorted(RAW_DIR.glob("*.csv"))
    print(f"Encontrados {len(raw_csvs)} arquivo(s) raw em CSV.\n")
    for f in raw_csvs:
        migrate_file(f, args.apply)

    print("\n=== Migrando data/df_batters_*.csv e data/df_pitchers_*.csv ===")
    agg_csvs = sorted(DATA_DIR.glob("df_batters_*.csv")) + sorted(DATA_DIR.glob("df_pitchers_*.csv"))
    print(f"Encontrados {len(agg_csvs)} arquivo(s) agregado(s) em CSV.\n")
    for f in agg_csvs:
        migrate_file(f, args.apply)

    if not args.apply:
        print("\nModo dry-run (nada foi alterado). Rode com --apply para migrar de fato.")
    else:
        print("\nMigração concluída.")


if __name__ == "__main__":
    main()
