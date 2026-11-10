from directrent.config import Settings

REQUIRED = {
    "BOT_TOKEN": "x", "TG_API_ID": "1", "TG_API_HASH": "h", "ANTHROPIC_API_KEY": "k",
    "DATABASE_URL": "postgresql://u:p@localhost/db", "ADMIN_TG_ID": "7",
}


def test_settings_parses_channels(monkeypatch):
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("TG_CHANNELS", "lviv_rent, @kvartyry_lviv")
    s = Settings(_env_file=None)
    assert s.tg_channels == ["lviv_rent", "kvartyry_lviv"]
    assert s.llm_daily_max_calls == 500
