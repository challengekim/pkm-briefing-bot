#!/usr/bin/env python3
"""Interactive setup wizard for PKM Briefing Bot."""

import os
import sys


def main():
    print("\n" + "=" * 50)
    print("  Compound Brain — Setup Wizard")
    print("=" * 50 + "\n")

    config = {}
    env = {}

    # 1. Language
    lang = input("Language (ko/en) [ko]: ").strip() or "ko"
    config["language"] = lang

    # 2. LLM Provider
    print("\n--- AI Model ---")
    print("Choose your LLM provider:\n")

    providers = [
        ("gemini", "Gemini", "Free tier: 1,500 req/day, no credit card"),
        ("openrouter", "OpenRouter", "100+ models from all providers, some free"),
        ("openai", "OpenAI", "GPT-4o, GPT-4o-mini"),
        ("anthropic", "Anthropic", "Claude Opus 4.6, Sonnet 4.6, Haiku 4.5"),
        ("ollama", "Ollama", "100% free, runs locally on your machine"),
    ]

    for i, (_, name, desc) in enumerate(providers, 1):
        print(f"  {i}. {name:14s} — {desc}")

    choice = input("\nSelect provider [1]: ").strip() or "1"
    idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(providers) else 0
    provider = providers[idx][0]

    # Model selection per provider
    model_options = {
        "gemini": [
            ("gemini-2.5-flash", "recommended, fast & free"),
            ("gemini-2.5-pro", "higher quality, paid"),
        ],
        "openrouter": [
            ("google/gemini-2.5-flash-preview-05-20:free", "free, recommended"),
            ("meta-llama/llama-4-maverick:free", "free"),
            ("mistralai/mistral-small-3.1-24b-instruct:free", "free"),
            ("qwen/qwen3-235b-a22b:free", "free"),
            ("anthropic/claude-sonnet-4", "~$3/mo"),
            ("anthropic/claude-haiku-4-5", "~$0.3/mo"),
            ("openai/gpt-4o-mini", "~$0.5/mo"),
            ("openai/gpt-4o", "~$5/mo"),
        ],
        "openai": [
            ("gpt-4o-mini", "recommended, ~$0.5/mo"),
            ("gpt-4o", "higher quality, ~$5/mo"),
            ("gpt-4.1-mini", "latest mini"),
            ("gpt-4.1", "latest"),
        ],
        "anthropic": [
            ("claude-haiku-4-5-20251001", "fast & cheap, ~$0.3/mo"),
            ("claude-sonnet-4-5-20250514", "balanced, ~$3/mo"),
            ("claude-opus-4-6-20250610", "most capable, ~$15/mo"),
        ],
        "ollama": [
            ("llama3.1:8b", "recommended, 4.7GB"),
            ("llama3.1:70b", "high quality, 40GB"),
            ("qwen2.5:7b", "good multilingual"),
            ("mistral:7b", "fast"),
        ],
    }

    models = model_options.get(provider, [])
    if models:
        print(f"\nAvailable models:")
        for i, (model_id, desc) in enumerate(models, 1):
            print(f"  {i}. {model_id} ({desc})")
        print(f"  {len(models) + 1}. Custom model name")

        mchoice = input(f"\nSelect model [1]: ").strip() or "1"
        midx = int(mchoice) - 1 if mchoice.isdigit() and 1 <= int(mchoice) <= len(models) else 0

        if mchoice.isdigit() and int(mchoice) == len(models) + 1:
            model = input("Enter model name: ").strip()
        elif 0 <= midx < len(models):
            model = models[midx][0]
        else:
            model = models[0][0]
    else:
        model = input("Enter model name: ").strip()

    config["llm"] = {"provider": provider, "model": model}

    # API key
    api_key_urls = {
        "gemini": ("https://aistudio.google.com/apikey", "Free tier: 1,500 requests/day — more than enough"),
        "openrouter": ("https://openrouter.ai/keys", "Free models require no payment — just sign up"),
        "openai": ("https://platform.openai.com/api-keys", ""),
        "anthropic": ("https://console.anthropic.com/settings/keys", ""),
    }

    if provider == "ollama":
        print("\nNo API key needed for Ollama.")
        print("Make sure Ollama is running: ollama serve")
    else:
        url, note = api_key_urls[provider]
        print(f"\nGet your API key at: {url}")
        if note:
            print(f"({note})")
        api_key = input("API Key: ").strip()
        env_key = "GEMINI_API_KEY" if provider == "gemini" else "LLM_API_KEY"
        env[env_key] = api_key

    # 3. Telegram Bot
    print("\n--- Telegram Bot ---")
    print("How to create a Telegram bot (1 minute):\n")
    print("  1. Open Telegram on your phone or desktop")
    print("  2. Search for @BotFather and start a chat")
    print("  3. Send: /newbot")
    print("  4. Choose a name (e.g. 'My Compound Brain')")
    print("  5. Choose a username (e.g. 'my_compound_brain_bot')")
    print("  6. BotFather gives you a token like: 123456:ABC-DEF...")
    print()
    bot_token = input("Paste your bot token here: ").strip()
    env["TELEGRAM_BOT_TOKEN"] = bot_token

    # Auto-detect chat_id
    print("\nNow send ANY message to your bot in Telegram.")
    print("(Open the bot chat and type 'hello')")
    input("Press Enter after sending a message...")

    import requests
    chat_id = ""
    try:
        resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates", timeout=10)
        if resp.ok:
            results = resp.json().get("result", [])
            for r in results:
                cid = r.get("message", {}).get("chat", {}).get("id")
                if cid:
                    chat_id = str(cid)
                    break
    except Exception:
        pass

    if chat_id:
        print(f"✓ Chat ID detected: {chat_id}")
    else:
        print("Could not auto-detect. Enter manually:")
        print(f"  Visit: https://api.telegram.org/bot{bot_token}/getUpdates")
        print("  Find 'chat':{'id': NUMBER} in the response")
        chat_id = input("Chat ID: ").strip()
    env["TELEGRAM_CHAT_ID"] = chat_id

    # 4. Vault path
    print("\n--- Knowledge Vault ---")
    print("Where do you store your markdown notes?")
    vault = input("Vault path [./vault]: ").strip() or "./vault"
    config["vault"] = {
        "path": vault,
        "scan_paths": [
            "10_Knowledge/References/AI Engineering",
            "10_Knowledge/References/AI Tools",
            "10_Knowledge/References/Business",
            "10_Knowledge/References/Engineering",
            "10_Knowledge/References/Marketing",
            "00_Inbox/Read Later",
        ],
        "ideas_file": "20_Projects/AI Ideas/project-ideas.md",
    }

    # Create vault from template if path doesn't exist
    if not os.path.exists(vault) and os.path.exists("vault_template"):
        import shutil

        shutil.copytree("vault_template", vault)
        print(f"Created vault structure at {vault}")

    # 5. Projects
    print("\n--- Your Projects ---")
    print("Enter projects (empty name to finish):")
    projects = []
    while True:
        name = input("  Project name: ").strip()
        if not name:
            break
        desc = input("  Description: ").strip()
        repo = input("  Repo path (optional): ").strip()
        p = {"name": name, "description": desc}
        if repo:
            p["repo_path"] = repo
        projects.append(p)
    config["projects"] = projects or [{"name": "My Project", "description": "Description"}]

    # 6. Schedule
    print("\n--- Schedule ---")
    tz = input("Timezone [Asia/Seoul]: ").strip() or "Asia/Seoul"
    config["schedule"] = {
        "timezone": tz,
        "trend": "10:00",
        "linkedin": "11:30",
        "knowledge": "sat 10:00",
        "meta": "1st 11:00",
    }

    # 7. Trends
    config["trends"] = {
        "subreddits": ["artificial", "MachineLearning", "LocalLLaMA", "singularity", "ChatGPT"],
        "hn_limit": 15,
        "reddit_limit": 8,
        "geeknews_limit": 10,
    }

    # Write config.yaml
    import yaml

    with open("config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print("\n✓ config.yaml created")

    # Write .env
    with open(".env", "w") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")
    print("✓ .env created")

    # Validate
    print("\n--- Validation ---")
    try:
        from config import Config

        Config()
        print("✓ Config loads successfully")
    except Exception as e:
        print(f"✗ Config error: {e}")

    print("\n" + "=" * 50)
    print("  Setup complete!")
    print("=" * 50)
    py = "python" if sys.platform == "win32" else "python3"
    print(f"\n  Save:  {py} main.py --save <URL>")
    print(f"  Test:  {py} main.py --test trend")
    print(f"  Run:   {py} main.py")
    print(f"\n  Or just send a URL to your Telegram bot!")


if __name__ == "__main__":
    main()
