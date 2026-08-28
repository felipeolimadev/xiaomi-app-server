# Xiaomi App Server — Notas do Projeto

## Visão Geral

Repositório que automaticamente sincroniza APKs de apps Xiaomi/HyperOS do Telegram para GitHub Releases, mantendo um catálogo JSON (`data/apps.json`) como fonte de dados para uma futura interface web.

---

## Decisões Tomadas

1. **Todos os APKs** — sem filtro, captura tudo que aparecer nos canais
2. **Separação por região** — cada versão inclui campo `region` (china, global, eea, india, etc.). O nome do arquivo também inclui a região: `com.miui.home_v4.39.14_global.apk`
3. **Histórico completo** — todas as versões são mantidas no catálogo e como assets nos Releases
4. **Tudo no GitHub Actions** — nada roda localmente, exceto o `generate_session.py` (uma única vez para gerar a StringSession do Telegram)
5. **Um Release por app** — tag = package_name (ex: `com.miui.home`)
6. **Deduplicação** — chave `(package_name, version_code, region)` em duas camadas:
   - Telegram: `min_id` pula mensagens já processadas
   - Catálogo: verifica se a combinação já existe

---

## Canais Monitorados

| Canal | URL | Foco |
|-------|-----|------|
| @hyperossystemapps | https://t.me/hyperossystemapps | Apps de sistema HyperOS |
| @MiuiSystemUpdater | https://t.me/MiuiSystemUpdater | Atualizações MIUI/HyperOS |
| @HyperOsUpdates | https://t.me/HyperOsUpdates | Atualizações gerais HyperOS |

---

## Estrutura de Arquivos

```
xiaomi-app-server/
├── .github/workflows/
│   └── sync-apks.yml              ← Cron a cada hora + trigger manual
├── scripts/
│   ├── generate_session.py        ← Gera StringSession (rodar 1x local)
│   ├── apk_metadata.py           ← Extrai metadata do APK (androguard)
│   ├── telegram_scraper.py       ← Scraper dos canais Telegram (telethon)
│   ├── github_releases.py        ← Gerencia releases via gh CLI
│   ├── catalog.py                ← CRUD do apps.json com suporte a região
│   └── main.py                   ← Orquestrador principal
├── data/
│   ├── apps.json                  ← Catálogo (atualizado automaticamente)
│   └── state.json                 ← Estado do scraper (message IDs por canal)
├── .gitignore
├── requirements.txt               ← telethon, cryptg, androguard
├── README.md
└── NOTES.md                       ← Este arquivo
```

---

## Schema do apps.json

```json
{
  "last_updated": "2026-08-28T15:00:00Z",
  "apps": {
    "com.miui.home": {
      "name": "Mi Launcher",
      "package_name": "com.miui.home",
      "latest_version": "4.39.14.7554",
      "latest_version_code": 414739014,
      "updated_at": "2026-08-28T14:30:00Z",
      "versions": [
        {
          "version_name": "4.39.14.7554",
          "version_code": 414739014,
          "region": "global",
          "file_name": "com.miui.home_v4.39.14.7554_global.apk",
          "file_size": 52428800,
          "download_url": "https://github.com/.../releases/download/com.miui.home/...",
          "min_sdk": 30,
          "target_sdk": 34,
          "source_channel": "@hyperossystemapps",
          "discovered_at": "2026-08-28T14:30:00Z"
        }
      ]
    }
  }
}
```

---

## Regiões Suportadas

Detecção automática a partir do texto do caption e nome do arquivo:
- `china` / `cn`
- `global` / `mi` / `international`
- `eea` / `europe`
- `india` / `in`
- `indonesia` / `id`
- `russia` / `ru`
- `turkey` / `tr`
- `taiwan` / `tw`
- `japan` / `jp`
- `korea` / `kr`
- `poco`
- `beta`
- `port`
- `unknown` (fallback)

---

## Setup Necessário

### Secrets do GitHub (Settings → Secrets → Actions)

| Secret | Descrição | Como obter |
|--------|-----------|------------|
| `TELEGRAM_API_ID` | ID numérico | [my.telegram.org](https://my.telegram.org) → API Development Tools |
| `TELEGRAM_API_HASH` | Hash alfanumérico | Mesmo lugar acima |
| `TELEGRAM_STRING_SESSION` | Sessão serializada | Rodar `python scripts/generate_session.py` localmente 1x |

> `GITHUB_TOKEN` é provido automaticamente pelo Actions.

### Gerar StringSession

```bash
pip install telethon
python scripts/generate_session.py
# Vai pedir: API_ID, API_HASH, telefone, código SMS, senha 2FA (se tiver)
# Copiar a string gerada e colar como Secret no GitHub
```

---

## Próximo Passo Planejado

- Interface web para download dos APKs, consumindo o `apps.json` como fonte de dados
- Filtros por app, região, versão
- Links diretos para download via GitHub Releases

---

## Limites e Considerações

- **GitHub Actions free**: 2000 min/mês. Cron 1h ≈ 720 runs/mês, cada run ~30s-2min
- **GitHub Releases**: Sem limite de storage para repos públicos (fair use)
- **Limite por asset**: 2GB por arquivo (APKs são tipicamente 5-200MB)
- **Telegram MTProto**: Sem limite de download de arquivo (vs Bot API que limita a 20MB)
- **StringSession**: Dá acesso total à conta Telegram — se vazar, revogar imediatamente
