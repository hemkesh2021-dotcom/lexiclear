"""Settings resolve their .env file independently of the working directory."""

from app.core.config import ENV_FILES, Settings


def test_env_files_are_absolute_and_include_the_repository_root():
    assert all(path.is_absolute() for path in ENV_FILES)
    assert ENV_FILES[0].parent.joinpath("backend").is_dir()


def test_the_key_is_read_from_the_root_env_file_whatever_the_cwd(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("LEXICLEAR_GOOGLE_API_KEY=from-root-env\n")
    monkeypatch.delenv("LEXICLEAR_GOOGLE_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path / "..")  # somewhere unrelated
    settings = Settings(_env_file=(env,))
    assert settings.google_api_key.get_secret_value() == "from-root-env"


def test_the_configured_env_file_setting_is_the_absolute_tuple():
    assert Settings.model_config["env_file"] == ENV_FILES
