from audacity_labels_to_csv import convert
from facilitator.sim_sources import load_labels


def test_audacity_export_becomes_label_csv(tmp_path):
    src = tmp_path / "labels.txt"
    src.write_text("12.500000\t31.000000\t1\n\\\t100.0\t2000.0\n33.2\t52.8\t2\n53.0\t54.0\trobot\n60.0\t70.5\t3\n")
    n = convert(str(src), str(tmp_path / "out.csv"))
    assert n == 3
    assert load_labels(str(tmp_path / "out.csv")) == [(12.5, 31.0, 0), (33.2, 52.8, 1), (60.0, 70.5, 2)]
