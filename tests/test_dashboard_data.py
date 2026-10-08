"""Small synthetic coverage for BWEB preparation and dashboard queries."""
import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("duckdb")
pytest.importorskip("pyarrow")

import dashboard_data as data
import prepare_ce_data as prep


@pytest.fixture
def con(tmp_path):
    rows = []
    base = {
        "SG_UF": "CE", "CD_MUNICIPIO": "13897", "NM_MUNICIPIO": "Fortaleza",
        "NR_ZONA": "001", "NR_SECAO": "0001", "NR_LOCAL_VOTACAO": "0123",
        "NR_URNA_EFETIVADA": "1", "SG_PARTIDO": "P1", "NM_PARTIDO": "Partido Um", "QT_APTOS": 100,
        "QT_COMPARECIMENTO": 70, "QT_ABSTENCOES": 30, "CATEGORIA_VOTO": "VALIDO_NOMINAL",
        "site_id": "CE|13897|001|0123", "NM_LOCAL_VOTACAO": "Local não identificado",
        "DS_ENDERECO": "Endereço não informado", "DS_BAIRRO": "Bairro não informado",
        "VL_LATITUDE": None, "VL_LONGITUDE": None,
    }
    # Candidate Ana is absent from section 2; election metrics still occur there.
    for section, cargo, number, name, party, kind, category, votes, aptos, turnout, abst in [
        ("0001", "Presidente", "10", "Ana", "P1", "Nominal", "VALIDO_NOMINAL", 10, 100, 70, 30),
        ("0001", "Presidente", "20", "Bia", "P1", "Nominal", "VALIDO_NOMINAL", 4, 100, 70, 30),
        ("0001", "Governador", "30", "Caio", "P1", "Nominal", "VALIDO_NOMINAL", 8, 100, 70, 30),
        ("0001", "Presidente", "95", "Branco", "", "Branco", "BRANCO", 2, 100, 70, 30),
        ("0002", "Presidente", "20", "Bia", "P1", "Nominal", "VALIDO_NOMINAL", 6, 80, 50, 30),
        ("0002", "Presidente", "21", "Bia", "P2", "Nominal", "VALIDO_NOMINAL", 3, 80, 50, 30),
        ("0002", "Presidente", "96", "Nulo", "", "Nulo", "NULO", 1, 80, 50, 30),
    ]:
        rows.append({**base, "NR_SECAO": section, "DS_CARGO_PERGUNTA": cargo,
                     "NR_VOTAVEL": number, "SG_PARTIDO": party, "NM_VOTAVEL": name,
                     "candidate_id": prep.make_candidate_id(number, name, party),
                     "DS_TIPO_VOTAVEL": kind,
                     "CATEGORIA_VOTO": category, "QT_VOTOS": votes,
                     "QT_APTOS": aptos, "QT_COMPARECIMENTO": turnout, "QT_ABSTENCOES": abst})
    path = tmp_path / "tiny.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    connection = data.open_data(path)
    yield connection
    connection.close()


def test_repeated_metrics_filters_and_site_group(con):
    summary = data.get_summary(con, {"municipio": "13897"})
    assert summary == {
        "votos_total": 34, "validos": 31, "brancos": 2, "nulos": 1,
        "aptos": 180, "comparecimento": 120, "abstencoes": 60,
    }
    by_cargo = data.get_summary(con, {"municipio": "13897", "cargo": "Presidente"})
    assert by_cargo["aptos"] == 180  # cargo filters do not limit turnout
    assert by_cargo["votos_total"] == 26
    ana_id = prep.make_candidate_id("10", "Ana", "P1")
    by_candidate = data.get_summary(con, {"municipio": "13897", "candidato": ana_id})
    assert by_candidate["aptos"] == 180  # turnout includes the section without Ana
    assert by_candidate["votos_total"] == 10

    points = data.get_map_points(con, {"municipio": "13897"})
    assert len(points) == 1
    assert points.iloc[0].site_id == "CE|13897|001|0123"
    assert points.iloc[0].TOTAL_VOTOS == 34
    assert pd.isna(points.iloc[0].VL_LATITUDE)
    assert points.iloc[0].DS_ENDERECO == "Endereço não informado"

    options = data.get_filter_options(con, {"municipio": "13897"})
    assert options["cargo"] == ["Governador", "Presidente"]
    assert len(options["candidato"]) == 4
    assert options["partido"] == ["P1", "P2"]
    labels = data.get_filter_labels(con, {"municipio": "13897"})
    assert labels["municipio"]["13897"] == "Fortaleza (13897)"
    assert labels["zona"]["001"] == "Zona 001"
    assert labels["local"]["0123"] == "Local não identificado (0123)"
    assert labels["secao"]["0001"] == "Seção 0001"
    assert labels["candidato"][ana_id] == "Ana — P1 — nº 10"
    candidates = data.get_candidate_votes(con, {"cargo": "Presidente"})
    assert set(candidates.NM_VOTAVEL) == {"Ana", "Bia"}
    detail = data.get_site_detail(con, "CE|13897|001|0123", {"cargo": "Presidente"})
    assert detail.QT_VOTOS.sum() == 26


def test_code_normalization_keeps_text_and_pads_numeric_codes():
    source = pd.Series(["13897", "1", "123", "ABC", "  "])
    normalized = prep.normalize_code(source, 5).tolist()
    assert normalized[:4] == ["13897", "00001", "00123", "ABC"]
    assert pd.isna(normalized[4])
    assert prep.make_candidate_id("10", "A|B", "P1") != prep.make_candidate_id("10", "A", "B|P1")


def test_filter_options_and_labels_can_be_limited_to_requested_keys(con):
    options = data.get_filter_options(con, {"municipio": "13897"}, keys=(key for key in ["local", "candidato"]))
    labels = data.get_filter_labels(con, {"municipio": "13897"}, keys=["local"])

    assert list(options) == ["local", "candidato"]
    assert options["local"] == ["0123"]
    assert len(options["candidato"]) == 4
    assert labels == {"local": {"0123": "Local não identificado (0123)"}}

    # Omitting keys retains the original all-options/all-labels API contract.
    assert list(data.get_filter_options(con, {"municipio": "13897"})) == list(data.FILTER_COLUMNS)
    assert list(data.get_filter_labels(con, {"municipio": "13897"})) == list(data.FILTER_COLUMNS)
    with pytest.raises(ValueError):
        data.get_filter_options(con, {}, keys=["missing"])


def test_prepare_scopes_ce_and_joins_normalized_tse_keys(tmp_path):
    from prepare_ce_data import KEY_COLUMNS

    def row(uf):
        values = {column: "" for column in KEY_COLUMNS}
        values.update({
            "SG_UF": uf, "CD_MUNICIPIO": "13897", "NM_MUNICIPIO": "Fortaleza",
            "NR_ZONA": "1", "NR_SECAO": "1", "NR_LOCAL_VOTACAO": "123",
            "NR_URNA_EFETIVADA": "1", "CD_CARGO_PERGUNTA": "1", "DS_CARGO_PERGUNTA": "Presidente",
            "NR_PARTIDO": "1", "SG_PARTIDO": "P1", "NM_PARTIDO": "Partido",
            "CD_TIPO_VOTAVEL": "1", "DS_TIPO_VOTAVEL": "Nominal", "NR_VOTAVEL": "10",
            "NM_VOTAVEL": "Candidata", "QT_VOTOS": "5", "QT_APTOS": "100",
            "QT_COMPARECIMENTO": "70", "QT_ABSTENCOES": "30",
        })
        return values

    source = tmp_path / "bweb.csv"
    pd.DataFrame([row("CE"), row("SP")], columns=KEY_COLUMNS).to_csv(
        source, sep=";", index=False, encoding="cp1252"
    )
    locations = tmp_path / "locais.csv"
    pd.DataFrame([{
        "SG_UF": "ce", "CD_MUNICIPIO": "13897", "NR_ZONA": "1", "NR_LOCAL_VOTACAO": "0123",
        "NM_LOCAL_VOTACAO": "Escola São José", "DS_ENDERECO": "Rua Teste, 1", "NM_BAIRRO": "Centro",
        "NR_LATITUDE": "-3,7123", "NR_LONGITUDE": "-38,5234",
    }]).to_csv(locations, sep=";", index=False, encoding="cp1252")
    output = tmp_path / "ce.parquet"
    prep.prepare(source, output, locations, chunksize=1)
    result = pd.read_parquet(output)
    assert result.SG_UF.tolist() == ["CE"]
    assert result.CD_MUNICIPIO.tolist() == ["13897"]
    assert result.NR_ZONA.tolist() == ["1"]
    assert result.NR_LOCAL_VOTACAO.tolist() == ["0123"]
    assert result.NM_LOCAL_VOTACAO.tolist() == ["Escola São José"]
    assert result.DS_ENDERECO.tolist() == ["Rua Teste, 1"]
    assert result.DS_BAIRRO.tolist() == ["Centro"]
    assert result.VL_LATITUDE.tolist() == [-3.7123]
    assert result.VL_LONGITUDE.tolist() == [-38.5234]
    assert result.CATEGORIA_VOTO.tolist() == ["VALIDO_NOMINAL"]
