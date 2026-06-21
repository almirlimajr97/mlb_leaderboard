"""
build_stats.py
--------------
Lê todos os Parquets de data/raw/, agrega e gera (particionado por
temporada, para não esbarrar no limite de tamanho de arquivo do GitHub
conforme o histórico cresce):
    - data/df_batters_<season>.parquet
    - data/df_pitchers_<season>.parquet

Uso:
    python scripts/build_stats.py
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ── Caminhos ───────────────────────────────────────────────
RAW_DIR     = Path(__file__).parent.parent / "data" / "raw"
DATA_DIR    = Path(__file__).parent.parent / "data"

# ── Constantes ─────────────────────────────────────────────
NOT_AB = ["Walk", "Intent Walk", "Hit By Pitch", "Sac Fly", "Sac Bunt", "Catcher Interference"]
HITS   = ["Single", "Double", "Triple", "Home Run"]

# Eventos de baserunning que não representam uma plate appearance concluída
# (o batter não terminou o turno por causa dessa jogada). Não devem contar
# nem como PA nem como AB, mesmo quando aparecem como "event" de uma linha
# record_type == "pitch".
EXCLUDE_PA = "Pickoff|Caught Stealing|Runner Out|Balk|Wild Pitch|Stolen Base"


def load_raw() -> pd.DataFrame:
    """Lê e concatena todos os Parquets de data/raw/."""
    files = sorted(RAW_DIR.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"Nenhum Parquet encontrado em {RAW_DIR}")

    print(f"Carregando {len(files)} arquivo(s)...")
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_parquet(f))
        except Exception as e:
            print(f"  ⚠ Erro ao ler {f.name}: {e}")

    df = pd.concat(dfs, ignore_index=True)
    print(f"  Total de linhas: {len(df)}")

    # Alguns jogos (geralmente os que terminam perto da meia-noite) podem
    # ter sido coletados duas vezes em arquivos raw de datas adjacentes,
    # por uma inconsistência já corrigida no fetch_data.py. Remove
    # duplicatas exatas para não inflar PA/AB/BF.
    n_before = len(df)
    df = df.drop_duplicates()
    n_removed = n_before - len(df)
    if n_removed > 0:
        print(f"  ⚠ Removidas {n_removed} linha(s) duplicada(s) (jogos coletados 2x em arquivos raw distintos).")

    # Arquivos raw antigos (gerados antes da coluna game_type existir) não
    # têm essa coluna. Garante que ela sempre exista, tratando ausência
    # como Regular Season (comportamento padrão antes dos playoffs serem
    # incluídos no pipeline).
    if "game_type" not in df.columns:
        df["game_type"] = "R"
    else:
        df["game_type"] = df["game_type"].fillna("R")

    # Mesma lógica para series_description: arquivos antigos não têm essa
    # coluna, então preenchemos com um valor padrão razoável.
    if "series_description" not in df.columns:
        df["series_description"] = "Regular Season"
    else:
        df["series_description"] = df["series_description"].fillna("Regular Season")

    # Arquivos raw diferentes podem ter salvo "season" com tipos distintos
    # (int em alguns, string em outros — provável resíduo da migração para
    # Parquet ou de diferenças na resposta da API entre coletas). Como o
    # pandas não unifica tipos automaticamente no concat, isso faz com que
    # comparações como `df["season"] == 2025` (int) silenciosamente
    # ignorem linhas onde season ficou como "2025" (string) — foi a causa
    # raiz de jogos de playoff sumirem do agregado final. Força um tipo
    # único logo na carga, antes de qualquer outra operação.
    df["season"] = pd.to_numeric(df["season"], errors="coerce").astype("Int64")

    # Mesmo problema pode acontecer com "ref" (código YYYYMM, ex: "202509").
    # Aqui mantemos como string (não numérico) porque ref é usado como
    # código/label em vários pontos do pipeline e do front-end, não como
    # valor matemático — mas precisa ser um tipo ÚNICO e consistente, ou o
    # to_parquet() quebra ao tentar inferir um schema único para a coluna
    # (foi exatamente esse erro: ArrowInvalid ao misturar int e str em ref).
    df["ref"] = df["ref"].astype(str)

    return df


def calc_total_outs(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula total_outs por linha caso não exista ou precise ser recalculado."""
    conditions = [
        (df["record_type"] == "pitch") & df["event"].str.contains("Triple Play", na=False),
        (df["record_type"] == "pitch") & df["event"].str.contains("Double Play|Grounded Into DP", na=False),
        (df["record_type"] == "pitch") & (df["is_out"] == True),
        (df["record_type"] == "baserunning") & (df["is_out"] == True),
    ]
    df["total_outs"] = np.select(conditions, [3, 2, 1, 1], default=0)
    return df


def build_batters(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega cubo de batters por jogo/situação."""
    df_bat = df[df["record_type"] == "pitch"].copy()

    # Pré-calcula as colunas booleanas UMA VEZ, de forma vetorizada, em vez
    # de rodar uma lambda por grupo dentro do groupby (que é centenas de
    # vezes mais lento com datasets grandes — essa mudança reduziu o tempo
    # de build_batters de ~3min para poucos segundos).
    event = df_bat["event"]
    is_excluded   = event.str.contains(EXCLUDE_PA, na=False)
    event_notna   = event.notna()
    df_bat["is_pa"]      = event_notna & ~is_excluded
    df_bat["is_ab"]      = event_notna & ~event.isin(NOT_AB) & ~is_excluded
    df_bat["is_hit"]     = event.isin(HITS)
    df_bat["is_single"]  = event == "Single"
    df_bat["is_double"]  = event == "Double"
    df_bat["is_triple"]  = event == "Triple"
    df_bat["is_hr"]      = event == "Home Run"
    df_bat["is_bb"]      = event == "Walk"
    df_bat["is_ibb"]     = event == "Intent Walk"
    df_bat["is_so"]      = event == "Strikeout"
    df_bat["is_hbp"]     = event == "Hit By Pitch"
    df_bat["is_sf"]      = event == "Sac Fly"

    agg = (
        df_bat
        .groupby([
            "season", "ref", "game_pk", "game_date", "game_type", "series_description",
            "batting_team", "fielding_team",
            "batter", "batter_id", "bat_side", "batter_split",
            "men_on_base", "pitcher", "pitcher_id",
            "venue", "day_night", "home_away_batting",
        ], dropna=False)
        .agg(
            PA      =("is_pa",     "sum"),
            AB      =("is_ab",     "sum"),
            H       =("is_hit",    "sum"),
            singles =("is_single", "sum"),
            doubles =("is_double", "sum"),
            triples =("is_triple", "sum"),
            HR      =("is_hr",     "sum"),
            RBI     =("rbi",       "sum"),
            BB      =("is_bb",     "sum"),
            IBB     =("is_ibb",    "sum"),
            SO      =("is_so",     "sum"),
            HBP     =("is_hbp",    "sum"),
            SF      =("is_sf",     "sum"),
        )
        .reset_index()
    )

    agg["RBI"] = agg["RBI"].fillna(0).astype(int)
    return agg


def build_pitchers(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega cubo de pitchers por jogo/situação.

    Importante: outs de baserunning (caught stealing, pickoff) não têm a
    mesma granularidade de matchup que os pitches (sem batter_split,
    men_on_base coerente, etc.), então são agregados separadamente por
    pitcher+game_pk e somados ao final — caso contrário esses outs são
    perdidos e o IP fica subestimado.
    """
    df_pit = df[df["record_type"] == "pitch"].copy()

    # home_away_pitching é o inverso de home_away_batting
    df_pit["home_away_pitching"] = df_pit["home_away_batting"].map(
        {"home": "away", "away": "home", "Home": "Away", "Away": "Home"}
    )

    # Mesma otimização de build_batters: pré-calcula as colunas booleanas
    # vetorizadas uma vez, em vez de uma lambda por grupo no groupby.
    event = df_pit["event"]
    is_excluded = event.str.contains(EXCLUDE_PA, na=False)
    event_notna = event.notna()
    df_pit["is_bf"]      = event_notna & ~is_excluded
    df_pit["is_ab"]      = event_notna & ~event.isin(NOT_AB) & ~is_excluded
    df_pit["is_hit"]     = event.isin(HITS)
    df_pit["is_single"]  = event == "Single"
    df_pit["is_double"]  = event == "Double"
    df_pit["is_triple"]  = event == "Triple"
    df_pit["is_hr"]      = event == "Home Run"
    df_pit["is_bb"]      = event == "Walk"
    df_pit["is_ibb"]     = event == "Intent Walk"
    df_pit["is_so"]      = event == "Strikeout"
    df_pit["is_hbp"]     = event == "Hit By Pitch"
    df_pit["is_sf"]      = event == "Sac Fly"

    agg = (
        df_pit
        .groupby([
            "season", "ref", "game_pk", "game_date", "game_type", "series_description",
            "fielding_team", "batting_team",
            "pitcher", "pitcher_id", "pitch_hand", "pitcher_split",
            "men_on_base", "batter",
            "venue", "day_night", "home_away_pitching",
        ], dropna=False)
        .agg(
            BF        =("is_bf",       "sum"),
            AB        =("is_ab",       "sum"),
            H         =("is_hit",      "sum"),
            singles   =("is_single",   "sum"),
            doubles   =("is_double",   "sum"),
            triples   =("is_triple",   "sum"),
            HR        =("is_hr",       "sum"),
            BB        =("is_bb",       "sum"),
            IBB       =("is_ibb",      "sum"),
            SO        =("is_so",       "sum"),
            HBP       =("is_hbp",      "sum"),
            SF        =("is_sf",       "sum"),
            total_outs=("total_outs",  "sum"),
        )
        .reset_index()
    )

    # Outs de baserunning (caught stealing, pickoff) não carregam a mesma
    # granularidade de matchup dos pitches, então são somados à parte por
    # pitcher_id+game_pk (não pelo nome, que pode ter homônimos) e
    # distribuídos na primeira linha desse jogo.
    df_base = df[df["record_type"] == "baserunning"].copy()
    if not df_base.empty:
        base_outs = (
            df_base
            .groupby(["pitcher_id", "game_pk"], dropna=False)["total_outs"]
            .sum()
            .reset_index()
            .rename(columns={"total_outs": "baserunning_outs"})
        )

        # Identifica a primeira linha de cada pitcher_id+game_pk no agg para
        # receber os outs extras (evita duplicar contagem em várias linhas).
        first_idx = (
            agg.sort_values(["pitcher_id", "game_pk"])
            .groupby(["pitcher_id", "game_pk"])
            .head(1)
            .index
        )
        agg = agg.merge(base_outs, on=["pitcher_id", "game_pk"], how="left")
        agg["baserunning_outs"] = agg["baserunning_outs"].fillna(0)
        mask_first = agg.index.isin(first_idx)
        agg.loc[mask_first, "total_outs"] += agg.loc[mask_first, "baserunning_outs"]
        agg = agg.drop(columns=["baserunning_outs"])

    return agg


def main():
    df = load_raw()
    df = calc_total_outs(df)

    print("\nAgregando batters...")
    df_batters = build_batters(df)

    print("\nAgregando pitchers...")
    df_pitchers = build_pitchers(df)

    seasons = sorted(set(
        df_batters["season"].dropna().astype(int).unique().tolist() +
        df_pitchers["season"].dropna().astype(int).unique().tolist()
    ))

    print(f"\nSalvando por temporada ({len(seasons)} encontrada(s))...")
    for season in seasons:
        b_season = df_batters[df_batters["season"] == season]
        out_bat = DATA_DIR / f"df_batters_{season}.parquet"
        b_season.to_parquet(out_bat, index=False)

        p_season = df_pitchers[df_pitchers["season"] == season]
        out_pit = DATA_DIR / f"df_pitchers_{season}.parquet"
        p_season.to_parquet(out_pit, index=False)

        print(f"  {season}: batters={len(b_season)} linhas, pitchers={len(p_season)} linhas")

    print("\nConcluído!")


if __name__ == "__main__":
    main()
