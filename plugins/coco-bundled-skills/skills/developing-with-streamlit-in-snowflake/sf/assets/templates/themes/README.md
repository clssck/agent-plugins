# Snowflake Theme for Streamlit

Ready-to-apply theme matching Snowflake's brand aesthetic: primary `#29B5E8` (cyan), text `#11567F`, Inter + JetBrainsMono fonts bundled locally for Streamlit-in-Snowflake compatibility.

## Layout

```
themes/
└── snowflake/
    ├── .streamlit/config.toml   # the theme (canonical, hand-edited)
    └── static/*.ttf             # fonts referenced by config.toml fontFaces
```

The theme is a plain `config.toml` + the `.ttf` files it references. No generation pipeline, no pre-rendered variants — edit `snowflake/.streamlit/config.toml` directly.

## Applying the theme to an existing app

Copy the `snowflake/` directory into the user's project:

```bash
cp -r <SKILL_DIR>/assets/templates/themes/snowflake/.streamlit <user-project>/
cp -r <SKILL_DIR>/assets/templates/themes/snowflake/static       <user-project>/
```

Or, to merge into an existing `config.toml`, copy the `[theme]`, `[theme.sidebar]`, and `[[theme.fontFaces]]` sections manually — and make sure `[server] enableStaticServing = true` is set and the fonts exist at `<user-project>/static/`.

## Why fonts are bundled locally (SiS constraint)

Streamlit-in-Snowflake does not allow remote URL fetches at runtime, so font files must be bundled with the app and referenced with an `app/static/` URL prefix. The theme's `config.toml` shows the pattern:

```toml
[server]
enableStaticServing = true         # required for static files

[[theme.fontFaces]]
family = "Inter"
url = "app/static/Inter-Regular.ttf"   # note: app/ prefix required
weight = 400
```

If you swap fonts, keep this wiring intact — loading from Google Fonts or another CDN will silently fail when deployed to SiS.

## Font licensing

Bundled fonts are licensed under the [SIL Open Font License 1.1](https://openfontlicense.org/), which permits free use, redistribution, and modification:

| Font | Source |
|------|--------|
| Inter | [github.com/rsms/inter](https://github.com/rsms/inter) |
| JetBrains Mono | [github.com/JetBrains/JetBrainsMono](https://github.com/JetBrains/JetBrainsMono) |
