"""
Immute — One API contract. Any model. Zero client changes.
Live demo CLI for APIDays May 2026
"""

import os, time, sys
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.prompt import Prompt
from rich import box

load_dotenv()
console = Console()

# ─── Registry ────────────────────────────────────────────────────────────────
# This is the only place provider details live.
# Callers never see model IDs, endpoints, or SDK differences.

REGISTRY = {
    "default": {
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-6",
        "label": "Claude Sonnet 4.6",
        "cost_input": 3.00,
        "cost_output": 15.00,
    },
    "default-reasoning": {
        "provider": "anthropic",
        "model_id": "claude-opus-4-6",
        "label": "Claude Opus 4.6",
        "cost_input": 15.00,
        "cost_output": 75.00,
    },
    "default-fast": {
        "provider": "anthropic",
        "model_id": "claude-haiku-4-5-20251001",
        "label": "Claude Haiku 4.5",
        "cost_input": 0.80,
        "cost_output": 4.00,
    },
    "default-vision": {
        "provider": "openai",
        "model_id": "gpt-4o",
        "label": "GPT-4o",
        "cost_input": 2.50,
        "cost_output": 10.00,
    },
    "default-long": {
        "provider": "google",
        "model_id": "gemini-1.5-pro",
        "label": "Gemini 1.5 Pro",
        "cost_input": 1.25,
        "cost_output": 5.00,
    },
}

FALLBACK_CHAIN = {
    "default-reasoning": [
        {"provider": "openai",   "model_id": "gpt-4o",          "label": "GPT-4o"},
        {"provider": "google",   "model_id": "gemini-1.5-pro",   "label": "Gemini 1.5 Pro"},
    ]
}

# ─── Adapters ─────────────────────────────────────────────────────────────────
# One function per provider. The rest of the code never calls provider SDKs directly.

def call_anthropic(model_id: str, prompt: str, max_tokens: int = 300) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    start = time.time()
    msg = client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - start
    return {
        "text": msg.content[0].text,
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
        "latency": elapsed,
    }

def call_openai(model_id: str, prompt: str, max_tokens: int = 300) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    start = time.time()
    resp = client.chat.completions.create(
        model=model_id,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - start
    return {
        "text": resp.choices[0].message.content,
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
        "latency": elapsed,
    }

def call_google(model_id: str, prompt: str, max_tokens: int = 300) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel(model_id)
    start = time.time()
    resp = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": max_tokens},
    )
    elapsed = time.time() - start
    usage = resp.usage_metadata
    return {
        "text": resp.text,
        "input_tokens": usage.prompt_token_count,
        "output_tokens": usage.candidates_token_count,
        "latency": elapsed,
    }

ADAPTERS = {
    "anthropic": call_anthropic,
    "openai":    call_openai,
    "google":    call_google,
}

# ─── Core abstraction ─────────────────────────────────────────────────────────
# This is what callers use. They pass a logical name, never a provider or model.

def complete(logical_model: str, prompt: str, max_tokens: int = 300) -> dict:
    config = REGISTRY[logical_model]
    adapter = ADAPTERS[config["provider"]]
    result = adapter(config["model_id"], prompt, max_tokens)
    result["logical_model"] = logical_model
    result["provider"] = config["provider"]
    result["model_id"] = config["model_id"]
    result["label"] = config["label"]
    result["cost_per_input_m"] = config.get("cost_input", 0)
    result["cost_per_output_m"] = config.get("cost_output", 0)
    return result

def complete_with_fallback(logical_model: str, prompt: str, simulate_failures: list = None, max_tokens: int = 300) -> dict:
    """Try primary, then fallbacks. simulate_failures is a list of providers to pretend failed."""
    simulate_failures = simulate_failures or []
    config = REGISTRY[logical_model]
    chain = [{"provider": config["provider"], "model_id": config["model_id"], "label": config["label"]}]
    chain += FALLBACK_CHAIN.get(logical_model, [])

    for i, entry in enumerate(chain):
        tag = "PRIMARY" if i == 0 else f"FALLBACK {i}"
        if entry["provider"] in simulate_failures:
            console.print(f"  [red]✗[/red] [{tag}] [bold]{entry['label']}[/bold] — simulated [red]overloaded / unavailable[/red]")
            time.sleep(0.6)
            continue
        console.print(f"  [yellow]→[/yellow] [{tag}] Trying [bold]{entry['label']}[/bold]...", end="")
        try:
            adapter = ADAPTERS[entry["provider"]]
            start = time.time()
            result = adapter(entry["model_id"], prompt, max_tokens)
            elapsed = time.time() - start
            console.print(f" [green]✓ 200 OK[/green] ({elapsed:.2f}s)")
            result["logical_model"] = logical_model
            result["provider"] = entry["provider"]
            result["model_id"] = entry["model_id"]
            result["label"] = entry["label"]
            result["fallback_index"] = i
            result["tried"] = i + 1
            return result
        except Exception as e:
            console.print(f" [red]✗ {e}[/red]")
    raise RuntimeError("All providers failed")

# ─── Cost helper ──────────────────────────────────────────────────────────────

def calc_cost(result: dict) -> float:
    cost_in = result.get("cost_per_input_m")
    cost_out = result.get("cost_per_output_m")
    if cost_in is None or cost_out is None:
        for v in REGISTRY.values():
            if v["model_id"] == result.get("model_id"):
                cost_in = cost_in if cost_in is not None else v.get("cost_input", 0)
                cost_out = cost_out if cost_out is not None else v.get("cost_output", 0)
                break
    cost_in = cost_in or 0
    cost_out = cost_out or 0
    in_cost = (result.get("input_tokens", 0) / 1_000_000) * cost_in
    out_cost = (result.get("output_tokens", 0) / 1_000_000) * cost_out
    return in_cost + out_cost

# ─── UI helpers ───────────────────────────────────────────────────────────────

def print_header():
    console.print()
    title = Text()
    title.append("Immute", style="bold white")
    title.append("  —  One API contract. Any model. Zero client changes.", style="dim")
    console.print(Panel(title, style="blue", padding=(0, 2)))
    console.print()

def print_act(n: int, title: str, subtitle: str):
    console.print()
    console.print(Rule(f"[bold blue]Act {n}[/bold blue]  [white]{title}[/white]  [dim]{subtitle}[/dim]"))
    console.print()

def print_result(result: dict, show_cost: bool = True):
    global SESSION_COST
    cost = calc_cost(result)
    SESSION_COST += cost
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column(style="dim", width=16)
    t.add_column(style="white")
    t.add_row("Model",    f"[bold]{result['label']}[/bold]  [dim]({result['model_id']})[/dim]")
    t.add_row("Provider", result["provider"])
    t.add_row("Tokens",   f"[cyan]{result['input_tokens']}[/cyan] in / [cyan]{result['output_tokens']}[/cyan] out")
    t.add_row("Latency",  f"{result['latency']:.2f}s")
    if show_cost:
        t.add_row("Cost",  f"[yellow]${cost:.5f}[/yellow] [dim](this call)[/dim]  |  [bold yellow]${SESSION_COST:.5f}[/bold yellow] [dim](total so far)[/dim]")
    console.print(t)
    console.print(Panel(result["text"].strip(), title="[dim]response[/dim]", border_style="dim", padding=(0, 1)))

def wait(msg="Press [bold]Enter[/bold] to continue..."):
    console.print()
    Prompt.ask(f"[dim]{msg}[/dim]", default="")
    console.print()

# ─── Demo acts ────────────────────────────────────────────────────────────────

PROMPT = "In one sentence, what is an API abstraction layer and why does it matter?"
SESSION_COST = 0.0

def act1_unified_contract():
    print_act(1, "Unified contract", "same call, three providers")
    console.print("[dim]The caller uses one logical name. The registry decides which provider responds.[/dim]")
    console.print()

    models = ["default", "default-vision", "default-long"]
    labels = ["default  → Anthropic", "default-vision  → OpenAI", "default-long  → Google"]

    for logical, label in zip(models, labels):
        console.print(f"[bold]complete([/bold][green]\"{logical}\"[/green][bold], prompt)[/bold]  [dim]# {label}[/dim]")
        console.print()
        with console.status(f"[dim]calling {REGISTRY[logical]['label']}...[/dim]"):
            result = complete(logical, PROMPT)
        print_result(result)
        if logical != models[-1]:
            wait("Press Enter for next provider →")

def act2_model_swap():
    print_act(2, "Model swap", "config change only — zero client code changes")

    console.print("[dim]Watch the client call. It never changes.[/dim]")
    console.print()
    console.print(Panel(
        '[bold green]complete[/bold green]([green]"default"[/green], prompt)',
        title="[dim]client code — frozen[/dim]", border_style="dim", padding=(0,2)
    ))
    console.print()

    console.print("[bold]Before:[/bold]  [dim]REGISTRY[\"default\"] → claude-sonnet-4-6  ($15/1M output)[/dim]")
    console.print()
    with console.status("[dim]calling Claude Sonnet 4.6...[/dim]"):
        r1 = complete("default", PROMPT)
    print_result(r1)
    cost1 = calc_cost(r1)

    wait("Press Enter to swap registry to Haiku →")

    # Temporarily swap registry
    original = REGISTRY["default"].copy()
    REGISTRY["default"] = REGISTRY["default-fast"].copy()
    REGISTRY["default"]["cost_output"] = 4.00

    console.print("[bold]After:[/bold]   [dim]REGISTRY[\"default\"] → claude-haiku-4-5  ($4/1M output)  ← one line changed[/dim]")
    console.print()
    with console.status("[dim]calling Claude Haiku 4.5...[/dim]"):
        r2 = complete("default", PROMPT)
    print_result(r2)
    cost2 = calc_cost(r2)

    REGISTRY["default"] = original  # restore

    console.print()
    savings_pct = (1 - cost2 / cost1) * 100 if cost1 > 0 else 0
    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
    t.add_column("", style="dim")
    t.add_column("Model")
    t.add_column("Cost (this call)", justify="right")
    t.add_column("Client changed?", justify="center")
    t.add_row("Before", r1["label"], f"${cost1:.5f}", "[red]—[/red]")
    t.add_row("After",  r2["label"], f"${cost2:.5f}", "[green]No[/green]")
    t.add_row("",       "",          f"[green]{savings_pct:.0f}% cheaper[/green]", "")
    console.print(t)

def act3_fallback():
    print_act(3, "Smart routing + fallback", "two providers fail — client never knows")

    console.print("[dim]Primary (Anthropic) and Fallback 1 (OpenAI) are simulated as unavailable.[/dim]")
    console.print("[dim]The router silently tries the next provider in the chain.[/dim]")
    console.print()
    console.print(Panel(
        '[bold green]complete[/bold green]([green]"default-reasoning"[/green], prompt)',
        title="[dim]client code — still the same[/dim]", border_style="dim", padding=(0,2)
    ))
    console.print()

    result = complete_with_fallback(
        "default-reasoning",
        PROMPT,
        simulate_failures=["anthropic", "openai"],
    )

    console.print()
    console.print(f"[bold green]✓ Response delivered.[/bold green]  "
                  f"[dim]Served by:[/dim] [bold]{result['label']}[/bold]  "
                  f"[dim]({result['tried']} provider(s) tried, client saw nothing)[/dim]")
    console.print()
    print_result(result)

# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    print_header()

    # Show registry upfront
    t = Table(title="[bold]Model Registry[/bold]  [dim](config, not code)[/dim]",
              box=box.SIMPLE_HEAVY, padding=(0, 2), show_lines=False)
    t.add_column("Logical name",  style="green")
    t.add_column("Provider",      style="dim")
    t.add_column("Model",         style="white")
    t.add_column("Output $/1M",   justify="right", style="yellow")
    for name, cfg in REGISTRY.items():
        t.add_row(f'"{name}"', cfg["provider"], cfg["model_id"], f"${cfg['cost_output']:.2f}")
    console.print(t)

    console.print()
    global PROMPT
    PROMPT = Prompt.ask("[bold]Enter a custom prompt for the demo[/bold]", default=PROMPT)
    
    wait("Press Enter to start Act 1 →")

    act1_unified_contract()
    wait("Press Enter for Act 2 →")

    act2_model_swap()
    wait("Press Enter for Act 3 →")

    act3_fallback()

    console.print()
    console.print(Rule("[bold blue]Immute[/bold blue]  [dim]github.com/ado-trakic/immute[/dim]"))
    console.print()

if __name__ == "__main__":
    main()
