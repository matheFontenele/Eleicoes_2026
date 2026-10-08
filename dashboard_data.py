"""Read-only query helpers for the local election dashboard (DuckDB backend).

`get_filter_options` returns serializable filter values; the `candidato` value is
the stable JSON-array `candidate_id` generated during preparation, not a display
name. Call `get_filter_labels(con, filters)` to map every option value to its
human-readable label. Pass selected option values back in `filters`; all SQL
values are bound parameters, so the IDs remain safe to query.
"""
from __future__ import annotations

from pathlib import Path
from collections.abc import Iterable

import pandas as pd

FILTER_COLUMNS = {
    "municipio": "CD_MUNICIPIO", "zona": "NR_ZONA", "local": "NR_LOCAL_VOTACAO",
    "secao": "NR_SECAO", "cargo": "DS_CARGO_PERGUNTA", "partido": "SG_PARTIDO", "candidato": "candidate_id",
}
SITE_FIELDS = [
    "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO",
    "NM_LOCAL_VOTACAO", "DS_ENDERECO", "DS_BAIRRO", "VL_LATITUDE", "VL_LONGITUDE",
]
BALLOT_KEYS = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO", "NR_URNA_EFETIVADA"]


def open_data(parquet_path):
    """Open Parquet in DuckDB. Install duckdb (`pip install duckdb`) if needed."""
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("O dashboard requer DuckDB: instale com `pip install duckdb`.") from exc
    con = duckdb.connect(database=":memory:")
    # Use DuckDB's relation API: DuckDB 1.5 does not allow prepared parameters in
    # CREATE VIEW statements. Passing the path to read_parquet avoids SQL interpolation.
    con.read_parquet(str(Path(parquet_path).resolve())).create_view("votos")
    return con


def _where(filters, *, omit=()):
    clauses, params = [], []
    for key, col in FILTER_COLUMNS.items():
        val = (filters or {}).get(key)
        if key not in omit and val is not None and str(val) != "":
            clauses.append(f'"{col}" = ?')  # column names come only from the constant allowlist above
            params.append(str(val))
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def _rows(con, sql, params=()):
    return con.execute(sql, list(params)).fetchdf()


def _option_rows(con, key, filters):
    col = FILTER_COLUMNS[key]
    where, params = _where(filters, omit=(key,))
    type_condition = ""
    if key == "partido":
        type_condition = "DS_TIPO_VOTAVEL IN ('Nominal', 'Legenda')"
    elif key == "candidato":
        type_condition = "DS_TIPO_VOTAVEL = 'Nominal'"
    clauses = []
    if where:
        clauses.append(where.removeprefix(" WHERE "))
    clauses.append(f'"{col}" IS NOT NULL')
    if type_condition:
        clauses.append(type_condition)
    extra = {
        "municipio": '"NM_MUNICIPIO" AS municipio_nome',
        "local": '"NM_LOCAL_VOTACAO" AS local_nome',
        "partido": '"NM_PARTIDO" AS partido_nome',
        "candidato": '"NM_VOTAVEL" AS candidato_nome, "SG_PARTIDO" AS candidato_partido, "NR_VOTAVEL" AS candidato_numero',
    }.get(key)
    select = f'"{col}" AS value' + (f", {extra}" if extra else "")
    return _rows(con, f'SELECT DISTINCT {select} FROM votos WHERE {" AND ".join(clauses)} ORDER BY value', params)


def _requested_filter_keys(keys: Iterable[str] | None) -> list[str]:
    if keys is None:
        return list(FILTER_COLUMNS)
    if isinstance(keys, str):
        requested = [keys]
    else:
        requested = list(dict.fromkeys(keys))
    unknown = [key for key in requested if key not in FILTER_COLUMNS]
    if unknown:
        raise ValueError(f"Chaves de filtro desconhecidas: {', '.join(map(str, unknown))}")
    return requested


def get_filter_options(con, filters, keys: Iterable[str] | None = None) -> dict:
    """Return values only for `keys` (all seven by default for compatibility).

    Candidate values are stable IDs. Use `get_filter_labels` for display labels.
    """
    return {key: [str(v) for v in _option_rows(con, key, filters)["value"].tolist()]
            for key in _requested_filter_keys(keys)}


def get_filter_labels(con, filters, keys: Iterable[str] | None = None) -> dict[str, dict[str, str]]:
    """Return cascading `{filter_key: {option_value: readable_label}}` maps.

    Municipality/local labels include both the official name and code; candidate
    labels include name, party and candidate number. Option values remain the
    serializable strings returned by `get_filter_options`.
    """
    labels = {}
    for key in _requested_filter_keys(keys):
        rows = _option_rows(con, key, filters)
        rendered = {}
        for row in rows.itertuples(index=False):
            value = str(row.value)
            if key == "municipio":
                name = getattr(row, "municipio_nome", None)
                label = f"{name} ({value})" if pd.notna(name) and name else value
            elif key == "local":
                name = getattr(row, "local_nome", None)
                label = f"{name} ({value})" if pd.notna(name) and name else f"Local {value}"
            elif key == "zona":
                label = f"Zona {value}"
            elif key == "secao":
                label = f"Seção {value}"
            elif key == "candidato":
                name = getattr(row, "candidato_nome", None) or "Candidato"
                party = getattr(row, "candidato_partido", None)
                number = getattr(row, "candidato_numero", None)
                parts = [str(name)]
                if pd.notna(party) and party:
                    parts.append(str(party))
                if pd.notna(number) and number:
                    parts.append(f"nº {number}")
                label = " — ".join(parts)
            elif key == "partido":
                name = getattr(row, "partido_nome", None)
                label = f"{value} — {name}" if pd.notna(name) and name else value
            else:
                label = value
            rendered[value] = label
        labels[key] = rendered
    return labels


def get_summary(con, filters) -> dict:
    # Turnout exists at ballot level, not candidate level: candidate/party/cargo
    # selections must not discard sections with no matching candidate rows.
    geographic = {key: value for key, value in (filters or {}).items()
                  if key in ("municipio", "zona", "local", "secao")}
    where, params = _where(geographic)
    vote_where, vote_params = _where(filters)
    # Metrics repeat on every candidate row and for every cargo. Collapse each physical ballot
    # section/urna first, then sum. Including cargo here would multiply electorate metrics.
    keys = ", ".join(f'"{key}"' for key in BALLOT_KEYS)
    ballots = f"(SELECT {keys}, MAX(QT_APTOS) aptos, MAX(QT_COMPARECIMENTO) comparecimento, MAX(QT_ABSTENCOES) abstencoes FROM votos{where} GROUP BY {keys})"
    metric_rows = _rows(con, f"SELECT COALESCE(SUM(aptos),0) aptos, COALESCE(SUM(comparecimento),0) comparecimento, COALESCE(SUM(abstencoes),0) abstencoes FROM {ballots}", params).iloc[0]
    votes = _rows(con, f"SELECT COALESCE(SUM(QT_VOTOS),0) votos_total, COALESCE(SUM(CASE WHEN CATEGORIA_VOTO IN ('VALIDO_NOMINAL','VALIDO_LEGENDA') THEN QT_VOTOS ELSE 0 END),0) validos, COALESCE(SUM(CASE WHEN CATEGORIA_VOTO='BRANCO' THEN QT_VOTOS ELSE 0 END),0) brancos, COALESCE(SUM(CASE WHEN CATEGORIA_VOTO='NULO' THEN QT_VOTOS ELSE 0 END),0) nulos FROM votos{vote_where}", vote_params).iloc[0]
    return {"votos_total": int(votes.votos_total), "validos": int(votes.validos), "brancos": int(votes.brancos), "nulos": int(votes.nulos), "aptos": int(metric_rows.aptos), "comparecimento": int(metric_rows.comparecimento), "abstencoes": int(metric_rows.abstencoes)}


def get_candidate_votes(con, filters) -> pd.DataFrame:
    where, params = _where(filters)
    condition = "DS_TIPO_VOTAVEL = 'Nominal'"
    if where:
        where += " AND " + condition
    else:
        where = " WHERE " + condition
    return _rows(con, f"SELECT candidate_id, NM_VOTAVEL, SG_PARTIDO, SUM(QT_VOTOS)::BIGINT AS QT_VOTOS FROM votos{where} GROUP BY candidate_id, NM_VOTAVEL, SG_PARTIDO ORDER BY QT_VOTOS DESC, NM_VOTAVEL, candidate_id", params)


def get_map_points(con, filters) -> pd.DataFrame:
    where, params = _where(filters)
    fields = ", ".join(f'"{field}"' for field in SITE_FIELDS)
    sql = f"SELECT site_id, {fields}, SUM(QT_VOTOS)::BIGINT TOTAL_VOTOS, SUM(CASE WHEN CATEGORIA_VOTO IN ('VALIDO_NOMINAL','VALIDO_LEGENDA') THEN QT_VOTOS ELSE 0 END)::BIGINT VALIDOS, SUM(CASE WHEN CATEGORIA_VOTO='BRANCO' THEN QT_VOTOS ELSE 0 END)::BIGINT BRANCOS, SUM(CASE WHEN CATEGORIA_VOTO='NULO' THEN QT_VOTOS ELSE 0 END)::BIGINT NULOS FROM votos{where} GROUP BY site_id, {fields} ORDER BY site_id"
    points = _rows(con, sql, params)
    return points


def get_site_detail(con, site_id, filters):
    where, params = _where(filters)
    # Site ID is bound as a value; all other filter parameters remain bound as well.
    site_clause = "site_id = ?"
    sql = f"SELECT DS_CARGO_PERGUNTA, NM_VOTAVEL, SG_PARTIDO, CATEGORIA_VOTO, SUM(QT_VOTOS)::BIGINT AS QT_VOTOS FROM votos{where}{' AND ' if where else ' WHERE '}{site_clause} GROUP BY DS_CARGO_PERGUNTA, NM_VOTAVEL, SG_PARTIDO, CATEGORIA_VOTO ORDER BY DS_CARGO_PERGUNTA, QT_VOTOS DESC, NM_VOTAVEL"
    return _rows(con, sql, [*params, str(site_id)])
