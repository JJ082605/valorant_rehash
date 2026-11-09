import logging

from valo_settings.logging_setup import register_secret, setup_logging


def test_log_redacts_secret(tmp_path):
    root = logging.getLogger()
    before = list(root.handlers)
    log_file = tmp_path / "log.txt"
    register_secret("hunter2")
    setup_logging(log_file)
    try:
        logging.getLogger("valo_settings.test").info("pw=hunter2")
    finally:
        for h in root.handlers[:]:
            if h not in before:
                h.close()
                root.removeHandler(h)
    text = log_file.read_text(encoding="utf-8")
    assert "pw=***" in text and "hunter2" not in text
