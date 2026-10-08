"""Prepare CE BWEB CSV data as a dashboard-ready Parquet file.

Usage: python prepare_ce_data.py INPUT.csv [--output data/ce_votos.parquet]
       [--localities localidades.csv | --download-localities] [--chunksize 250000]

The BWEB input is read incrementally (45 columns, semicolon separated,
CP1252/Latin-1). Locality metadata is optional and is matched on UF,
municipality, zone and polling-place code. Parquet is written to a temporary
file first, so an interrupted run never replaces a previously valid output.
Requires pandas and pyarrow.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

TSE_LOCALITIES_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/"
    "eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip"
)


KEY_COLUMNS = [
    "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
    "NR_LOCAL_VOTACAO", "NR_URNA_EFETIVADA", "CD_CARGO_PERGUNTA",
    "DS_CARGO_PERGUNTA", "NR_PARTIDO", "SG_PARTIDO", "NM_PARTIDO",
    "CD_TIPO_VOTAVEL", "DS_TIPO_VOTAVEL", "NR_VOTAVEL", "NM_VOTAVEL",
    "QT_VOTOS", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
]
PLACE_COLUMNS = ["NM_LOCAL_VOTACAO", "DS_ENDERECO", "DS_BAIRRO", "VL_LATITUDE", "VL_LONGITUDE"]
PLACE_KEYS = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO"]
ID_COLUMNS = [
    "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO",
    "NR_URNA_EFETIVADA", "CD_CARGO_PERGUNTA", "NR_PARTIDO", "CD_TIPO_VOTAVEL", "NR_VOTAVEL",
]


def _text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace({"": pd.NA})


def normalize_code(series: pd.Series, width: int) -> pd.Series:
    """Match the repository's normalizar_codigo behavior, without losing text IDs."""
    text = series.astype("string").fillna("").str.strip()
    numeric = pd.to_numeric(text.where(text.ne("")), errors="coerce")
    result = text.copy()
    valid = numeric.notna()
    result.loc[valid] = numeric.loc[valid].astype("Int64").astype("string").str.zfill(width)
    return result.replace({"": pd.NA})


def make_candidate_id(number, name, party) -> str:
    """Create a stable, unambiguous, serializable candidate key."""
    components = ["" if pd.isna(value) else str(value) for value in (number, name, party)]
    return json.dumps(components, ensure_ascii=False, separators=(",", ":"))


def _normalize_place_keys(frame: pd.DataFrame) -> pd.DataFrame:
    for col, width in (("CD_MUNICIPIO", 5), ("NR_ZONA", 1), ("NR_LOCAL_VOTACAO", 4)):
        frame[col] = normalize_code(frame[col], width)
    frame["SG_UF"] = _text(frame["SG_UF"]).str.upper()
    return frame


def download_ce_localities(data_dir: Path) -> Path:
    """Download the TSE ZIP and safely extract its CE CSV into data_dir."""
    data_dir.mkdir(parents=True, exist_ok=True)
    archive = data_dir / "eleitorado_local_votacao_2026.zip"
    if not archive.exists():
        partial = archive.with_name(archive.name + ".part")
        try:
            with urllib.request.urlopen(TSE_LOCALITIES_URL, timeout=60) as response, partial.open("wb") as target:
                while block := response.read(1024 * 1024):
                    target.write(block)
            os.replace(partial, archive)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
    with zipfile.ZipFile(archive) as zipped:
        members = [name for name in zipped.namelist() if name.upper().endswith("_CE.CSV")]
        if not members:
            raise ValueError("O ZIP oficial do TSE não contém arquivo _CE.CSV")
        target = data_dir / Path(members[0]).name
        with zipped.open(members[0]) as source, target.open("wb") as destination:
            while block := source.read(1024 * 1024):
                destination.write(block)
    return target


def prepare(input_csv: Path, output: Path, localities: Path | None = None, chunksize: int = 250_000) -> None:
    location = None
    if localities:
        try:
            location = pd.read_csv(localities, sep=";", encoding="utf-8-sig", dtype="string", keep_default_na=False)
        except UnicodeDecodeError:
            # The official TSE locality package is Windows-1252; normalized input
            # tables may be UTF-8. Accept either without corrupting accented names.
            location = pd.read_csv(localities, sep=";", encoding="cp1252", dtype="string", keep_default_na=False)
        # The original TSE locality export uses these raw field names. Keep
        # normalized aliases intact when present, and fill only absent targets.
        aliases = {
            "NM_BAIRRO": "DS_BAIRRO",
            "NR_LATITUDE": "VL_LATITUDE",
            "NR_LONGITUDE": "VL_LONGITUDE",
        }
        for source, target in aliases.items():
            if target not in location.columns and source in location.columns:
                location = location.rename(columns={source: target})
        missing = set(PLACE_KEYS) - set(location.columns)
        if missing:
            raise ValueError(f"Tabela de localidades sem chaves obrigatórias: {', '.join(sorted(missing))}")
        _normalize_place_keys(location)
        for col in ("VL_LATITUDE", "VL_LONGITUDE"):
            if col in location.columns:
                location[col] = pd.to_numeric(
                    location[col].astype("string").str.strip().str.replace(",", ".", regex=False),
                    errors="coerce",
                ).astype("float64")
        keep = PLACE_KEYS + [c for c in PLACE_COLUMNS if c in location.columns]
        location = location[keep].drop_duplicates(PLACE_KEYS, keep="last")

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=output.parent)
    os.close(fd)
    writer = None
    try:
        for chunk in pd.read_csv(
            input_csv, sep=";", encoding="cp1252", dtype="string", usecols=lambda c: c in KEY_COLUMNS,
            chunksize=chunksize, keep_default_na=False, low_memory=False,
        ):
            missing = set(KEY_COLUMNS) - set(chunk.columns)
            if missing:
                raise ValueError(f"CSV BWEB sem colunas essenciais: {', '.join(sorted(missing))}")
            # The preparation output is deliberately scoped to Ceará, even if an input
            # file accidentally contains rows from multiple UFs.
            chunk["SG_UF"] = chunk["SG_UF"].str.upper()
            chunk = chunk.loc[chunk["SG_UF"].eq("CE")].copy()
            if chunk.empty:
                continue
            for col in chunk.columns:
                chunk[col] = _text(chunk[col])
            _normalize_place_keys(chunk)
            for col in ("QT_VOTOS", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES"):
                chunk[col] = pd.to_numeric(chunk[col], errors="coerce").fillna(0).astype("int64")
            if location is not None:
                chunk = chunk.merge(location, on=PLACE_KEYS, how="left", validate="many_to_one")
            else:
                for col in PLACE_COLUMNS:
                    chunk[col] = pd.NA
            for col, fallback in (("NM_LOCAL_VOTACAO", "Local não identificado"),
                                  ("DS_ENDERECO", "Endereço não informado"),
                                  ("DS_BAIRRO", "Bairro não informado")):
                chunk[col] = chunk[col].fillna(fallback)
            chunk["CATEGORIA_VOTO"] = chunk["DS_TIPO_VOTAVEL"].map({
                "Nominal": "VALIDO_NOMINAL", "Legenda": "VALIDO_LEGENDA", "Branco": "BRANCO", "Nulo": "NULO",
            }).fillna("OUTRO")
            chunk["VALIDOS"] = chunk["CATEGORIA_VOTO"].isin(["VALIDO_NOMINAL", "VALIDO_LEGENDA"])
            chunk["candidate_id"] = [make_candidate_id(number, name, party)
                                     for number, name, party in zip(
                                         chunk["NR_VOTAVEL"], chunk["NM_VOTAVEL"], chunk["SG_PARTIDO"])]
            # IDs are never parsed as numbers; concatenating fixed-width source values is stable.
            chunk["site_id"] = chunk[PLACE_KEYS].fillna("").astype("string").agg("|".join, axis=1)
            table = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(tmp_name, table.schema, compression="zstd")
            writer.write_table(table)
        if writer is None:
            raise ValueError("O CSV de entrada não contém linhas")
        writer.close()
        writer = None
        os.replace(tmp_name, output)
    except Exception:
        if writer is not None:
            writer.close()
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="CSV BWEB local")
    parser.add_argument("--output", type=Path, default=Path("data/ce_votos.parquet"))
    parser.add_argument("--localities", type=Path, help="CSV oficial opcional de locais do TSE, separado por ;")
    parser.add_argument("--download-localities", action="store_true", help="Baixa e usa automaticamente a tabela oficial TSE de locais do CE")
    parser.add_argument("--chunksize", type=int, default=250_000)
    args = parser.parse_args()
    if args.localities and args.download_localities:
        parser.error("Use --localities ou --download-localities, não ambos")
    localities = args.localities
    if args.download_localities:
        localities = download_ce_localities(Path("data"))
    prepare(args.input, args.output, localities, args.chunksize)
    print(f"Parquet pronto: {args.output}")


if __name__ == "__main__":
    main()
