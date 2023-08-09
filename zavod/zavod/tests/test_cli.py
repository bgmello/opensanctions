import shutil
from click.testing import CliRunner

from zavod import settings
from zavod.meta import Dataset
from zavod.cli import crawl, run, export, load_db, dump_file
from zavod.archive import dataset_state_path
from zavod.tests.conftest import DATASET_1_YML


def test_crawl_dataset():
    runner = CliRunner()
    result = runner.invoke(crawl, ["/dev/null"])
    assert result.exit_code != 0, result.output
    result = runner.invoke(crawl, [DATASET_1_YML.as_posix()])
    assert result.exit_code == 0, result.output


def test_export_dataset():
    runner = CliRunner()
    result = runner.invoke(export, ["/dev/null"])
    assert result.exit_code != 0, result.output
    result = runner.invoke(export, [DATASET_1_YML.as_posix()])
    assert result.exit_code == 0, result.output


def test_load_db():
    runner = CliRunner()
    db_path = dataset_state_path("x") / "dump.sqlite3"
    db_uri = "sqlite:///%s" % db_path.as_posix()
    result = runner.invoke(load_db, ["/dev/null", db_uri])
    assert result.exit_code != 0, result.output
    result = runner.invoke(load_db, [DATASET_1_YML.as_posix(), db_uri])
    assert result.exit_code == 0, result.output


def test_dump_file():
    runner = CliRunner()
    out_path = dataset_state_path("x") / "out.csv"
    result = runner.invoke(dump_file, ["/dev/null", out_path.as_posix()])
    assert result.exit_code != 0, result.output
    result = runner.invoke(dump_file, [DATASET_1_YML.as_posix(), out_path.as_posix()])
    assert result.exit_code == 0, result.output


def test_run_dataset(testdataset1: Dataset):
    latest_path = settings.ARCHIVE_PATH / "latest" / testdataset1.name
    assert not latest_path.exists()
    runner = CliRunner()
    result = runner.invoke(run, ["/dev/null"])
    assert result.exit_code != 0, result.output
    result = runner.invoke(run, ["--latest", DATASET_1_YML.as_posix()])
    assert result.exit_code == 0, result.output
    assert latest_path.exists()
    assert latest_path.joinpath("index.json").exists()
    assert latest_path.joinpath("entities.ftm.json").exists()
    shutil.rmtree(settings.ARCHIVE_PATH)
