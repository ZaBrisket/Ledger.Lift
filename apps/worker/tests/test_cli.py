from typer.testing import CliRunner
from worker.cli import app

def test_cli_process_document_runs():
    runner = CliRunner()
    result = runner.invoke(app, ["process-document", "00000000-0000-0000-0000-000000000000"])
    assert result.exit_code == 0
    assert "Processing document" in result.stdout
