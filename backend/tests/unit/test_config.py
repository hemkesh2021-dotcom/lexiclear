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


def test_cors_origins_accept_a_comma_separated_env_value(monkeypatch):
    monkeypatch.setenv("LEXICLEAR_CORS_ALLOW_ORIGINS", "http://a.example, http://b.example")
    assert Settings(_env_file=None).cors_allow_origins == ("http://a.example", "http://b.example")


def test_cors_origins_accept_a_single_env_value(tmp_path):
    env = tmp_path / ".env"
    env.write_text("LEXICLEAR_CORS_ALLOW_ORIGINS=http://localhost:5173\n")
    assert Settings(_env_file=(env,)).cors_allow_origins == ("http://localhost:5173",)


def test_the_shipped_env_example_parses_cleanly():
    from app.core.config import ENV_FILES

    example = ENV_FILES[0].with_name(".env.example")
    settings = Settings(_env_file=(example,))
    assert settings.cors_allow_origins
