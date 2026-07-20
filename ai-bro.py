#!/usr/local/casata/python-venv/bin/python3
import os
import sys
import json
import subprocess
import shlex
import google.generativeai as genai
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, Window, FormattedTextControl
from prompt_toolkit.styles import Style

# Imports opcionales para otros proveedores
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    from mistralai.client import Mistral
except ImportError:
    try:
        from mistralai import Mistral
    except ImportError:
        Mistral = None

try:
    import ollama as ollama_lib
except ImportError:
    ollama_lib = None

# --- DETECCIÓN DE OLLAMA ---
def is_ollama_installed():
    """Verifica si Ollama está instalado (librería Python y/o comando ollama)."""
    if ollama_lib is not None:
        return True
    try:
        subprocess.run(["which", "ollama"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

# --- CONFIGURACIÓN Y RUTAS ---
CONFIG_DIR = os.path.expanduser("~/.config/ai-bro")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
PWD = os.getcwd()
console = Console()

def load_config():
    default_config = {
        "api_key": "",
        "model": "gemini-2.0-flash",
        "preferences": "",
        "auto_approve": False,
        "provider": "gemini",
        "providers": {
            "gemini": {"api_key": "", "model": "gemini-2.0-flash"},
            "openai": {"api_key": "", "model": "gpt-4o-mini"},
            "claude": {"api_key": "", "model": "claude-opus-4-5-20251101"},
            "mistral": {"api_key": "", "model": "mistral-large-latest"},
            "deepseek": {"api_key": "", "model": "deepseek-chat"},
            "ollama": {"api_key": "ollama", "model": "llama3.1:latest"}
        }
    }

    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    if not os.path.exists(CONFIG_FILE):
        return default_config

    try:
        with open(CONFIG_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return default_config
            config = json.loads(content)

            if "preferences" not in config:
                config["preferences"] = ""
            if "auto_approve" not in config:
                config["auto_approve"] = False
            if "provider" not in config:
                config["provider"] = "gemini"

            if "providers" not in config:
                config["providers"] = {
                    "gemini": {"api_key": config.get("api_key", ""), "model": config.get("model", "gemini-2.0-flash")},
                    "openai": {"api_key": "", "model": "gpt-4o-mini"},
                    "claude": {"api_key": "", "model": "claude-3-5-sonnet-20241022"},
                    "mistral": {"api_key": "", "model": "mistral-large-latest"},
                    "deepseek": {"api_key": "", "model": "deepseek-chat"},
                    "ollama": {"api_key": "ollama", "model": "llama3.1:latest"}
                }
            else:
                for prov, defaults in default_config["providers"].items():
                    if prov not in config["providers"]:
                        config["providers"][prov] = defaults

            if not is_ollama_installed() and "ollama" in config["providers"]:
                del config["providers"]["ollama"]
                if config["provider"] == "ollama":
                    config["provider"] = "gemini"

            return config

    except json.JSONDecodeError:
        console.print("[bold yellow]⚠️ Archivo de configuración corrupto. Usando valores por defecto.[/bold yellow]")
        return default_config
    except Exception as e:
        console.print(f"[bold yellow]⚠️ Error al leer configuración: {e}. Usando valores por defecto.[/bold yellow]")
        return default_config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

config = load_config()
auto_approve_commands = config.get("auto_approve", False)

# --- FUNCIONES TIPO APT ---
def ask_apt_style(question, default="s"):
    choices = r"\[S/n]" if default.lower() == 's' else r"\[s/N]"
    answer = console.input(f"{question} {choices} ").strip().lower()
    if not answer:
        return default.lower()
    return 's' if answer.startswith('s') else 'n'

# --- SEGURIDAD Y SANDBOX ---
def is_safe_path(command_string):
    """Comprueba que los paths del comando estén dentro del directorio actual."""
    try:
        parts = shlex.split(command_string)
    except ValueError as e:
        console.print(f"[bold red]Error de sintaxis en el comando: {e}[/bold red]")
        return False

    for part in parts:
        if part.startswith('-'): continue
        if os.path.exists(part):
            abs_path = os.path.abspath(part)
            if not abs_path.startswith(PWD):
                return False
    return True

def validate_command_syntax(command):
    """Valida que el comando tenga sintaxis de shell correcta (comillas balanceadas)."""
    try:
        shlex.split(command)
        return True, ""
    except ValueError as e:
        return False, str(e)

def execute_safely(command):
    global auto_approve_commands

    console.print(f"\n[bold yellow]⚠️ La IA solicita ejecutar:[/bold yellow] [cyan]{command}[/cyan]")

    if auto_approve_commands:
        console.print("[bold green]✓ Ejecutando automáticamente (modo ss activo).[/bold green]")
        confirm = 's'
    else:
        confirm = ask_apt_style("¿Permitir ejecución?", default="s")

    if confirm != 's':
        return "El usuario denegó la ejecución del comando."

    if not is_safe_path(command):
        return "Error de seguridad: Intento de acceso fuera del directorio actual (PWD) o comando mal formado."

    try:
        result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, timeout=10)
        return result.decode('utf-8')
    except subprocess.CalledProcessError as e:
        return f"Error al ejecutar el comando. Salida: {e.output.decode('utf-8')}"
    except Exception as e:
        return f"Error del sistema: {str(e)}"

def execute_script(script_content):
    """Ejecuta un script bash guardándolo en un archivo temporal dentro de PWD."""
    global auto_approve_commands

    console.print(f"\n[bold yellow]📜 La IA solicita ejecutar un script multilínea.[/bold yellow]")
    if auto_approve_commands:
        console.print("[bold green]✓ Ejecutando automáticamente (modo ss activo).[/bold green]")
        confirm = 's'
    else:
        confirm = ask_apt_style("¿Permitir ejecución del script?", default="s")

    if confirm != 's':
        return "El usuario denegó la ejecución del script."

    tmp_path = os.path.join(PWD, ".ai_bro_tmp_script.sh")
    try:
        with open(tmp_path, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(script_content)
        os.chmod(tmp_path, 0o755)

        result = subprocess.check_output(
            tmp_path, shell=False, stderr=subprocess.STDOUT, timeout=30
        )
        return result.decode('utf-8')
    except subprocess.CalledProcessError as e:
        return f"Error al ejecutar el script. Salida:\n{e.output.decode('utf-8')}"
    except Exception as e:
        return f"Error del sistema: {str(e)}"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# --- MANEJO DE API KEY ---
def handle_api_key():
    provider = config.get("provider", "gemini")
    if provider == "ollama":
        console.print("[bold cyan]Ollama no necesita API Key (se ejecuta localmente).[/bold cyan]")
        return False
    current_key = config["providers"][provider].get("api_key", "")

    if current_key:
        masked_key = f"{current_key[:6]}...{current_key[-4:]}" if len(current_key) > 8 else current_key
        console.print(f"\n[bold cyan]API Key actual ({provider}):[/bold cyan] {masked_key}")
        default_answer = "n"
    else:
        console.print(f"\n[bold red]No hay ninguna API Key configurada para {provider}.[/bold red]")
        default_answer = "s"

    cambiar = ask_apt_style("¿Quieres cambiar la API Key?", default=default_answer)
    if cambiar == 's':
        new_key = console.input(f"[bold green]Ingresa tu nueva API Key para {provider}:[/bold green] ").strip()
        if new_key:
            config["providers"][provider]["api_key"] = new_key
            save_config(config)
            console.print("[bold blue]✓ API Key guardada exitosamente.[/bold blue]")
            return True
    return False

# --- SELECTOR INTERACTIVO MEJORADO ---
def interactive_select(options, title="Selecciona una opción"):
    """
    Selector interactivo con navegación por flechas y colores.
    Soporta:
      - string simple
      - (id, label)
      - (id, label, descripcion)
      - (id, lista_de_segmentos) donde cada segmento es (style_class, texto)
    """
    if not options:
        return None

    items = []
    for opt in options:
        if isinstance(opt, str):
            items.append((opt, None, None))
        elif isinstance(opt, tuple):
            if len(opt) == 2:
                id_, label = opt
                if isinstance(label, list):
                    items.append((id_, label, None))
                else:
                    items.append((id_, str(label), None))
            elif len(opt) == 3:
                id_, label, desc = opt
                if isinstance(label, list):
                    items.append((id_, label, desc))
                else:
                    items.append((id_, str(label), desc))
        else:
            items.append((str(opt), str(opt), None))

    current_idx = 0
    result = [None]

    def get_fragments():
        fragments = [
            ("class:title", f"  ╭── {title} ──╮\n"),
            ("class:border", "  │\n"),
        ]
        for i, (_, content, desc) in enumerate(items):
            selected = (i == current_idx)
            if isinstance(content, list):
                if selected:
                    fragments.append(("class:selected", "  ▶ "))
                    for style_class, text in content:
                        fragments.append(("class:selected", text))
                    fragments.append(("class:selected", "\n"))
                else:
                    fragments.append(("", "    "))
                    for style_class, text in content:
                        fragments.append((style_class, text))
                    fragments.append(("", "\n"))
            else:
                label = content
                if selected:
                    fragments.append(("class:selected", f"  ▶ {label}"))
                    if desc:
                        fragments.append(("class:selected_desc", f"  ({desc})"))
                    fragments.append(("class:selected", "\n"))
                else:
                    label_style = "class:option_even" if i % 2 == 0 else "class:option_odd"
                    fragments.append((label_style, f"    {label}"))
                    if desc:
                        fragments.append(("class:desc", f"  ({desc})"))
                    fragments.append(("", "\n"))
        fragments.append(("class:border", "  │\n"))
        fragments.append(("class:hint", "  ╰── ↑↓: mover  Enter: seleccionar  Esc: cancelar\n"))
        return fragments

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        nonlocal current_idx
        current_idx = (current_idx - 1) % len(items)
        event.app.invalidate()

    @kb.add("down")
    def _(event):
        nonlocal current_idx
        current_idx = (current_idx + 1) % len(items)
        event.app.invalidate()

    @kb.add("enter")
    def _(event):
        result[0] = items[current_idx][0]
        event.app.exit()

    @kb.add("escape")
    @kb.add("c-c")
    def _(event):
        result[0] = None
        event.app.exit()

    text_control = FormattedTextControl(get_fragments)
    window = Window(content=text_control, always_hide_cursor=True)
    layout = Layout(HSplit([window]))

    style = Style.from_dict({
        "title":         "bold cyan",
        "border":        "dim cyan",
        "selected":      "bg:#005f87 fg:white bold",
        "selected_desc": "bg:#005f87 fg:white italic",
        "option_even":   "fg:ansimagenta bold",
        "option_odd":    "fg:ansicyan bold",
        "desc":          "fg:ansiyellow italic",
        "hint":          "italic #ffd75f",
        "provider_name":  "fg:#ff8700 bold",
        "model_name":     "fg:ansimagenta",
        "api_ok":         "fg:ansigreen bold",
        "api_fail":       "fg:ansired bold",
        "current_marker": "fg:ansiyellow bold",
        "separator":      "fg:ansibrightblack",
        "model_id":       "fg:#ff8700 bold",
        "model_human":    "fg:#af5fff",
        "model_desc":     "fg:ansigreen italic",
    })

    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=False,
        erase_when_done=False,
    )

    app.run()
    return result[0]

# --- CAMBIO DE PROVEEDOR ---
def change_provider():
    providers = list(config["providers"].keys())
    current_provider = config.get("provider", "gemini")
    has_api_key = bool(config["providers"][current_provider].get("api_key", "")) or current_provider == "ollama"

    console.print(f"\n[bold cyan]Tu proveedor actual:[/bold cyan] {current_provider}")

    if has_api_key:
        question = "¿Quieres cambiar de proveedor?"
        default = "n"
    else:
        question = "¿Quieres cambiar de proveedor? (necesitas configurar API Key)"
        default = "s"

    if ask_apt_style(question, default=default) != "s":
        return False

    options = []
    for prov in providers:
        model = config["providers"][prov].get("model", "N/A")
        api_key = config["providers"][prov].get("api_key", "")
        if prov == "ollama":
            api_status = "✓ local"
            api_style = "class:api_ok"
        else:
            if api_key:
                api_status = "✓ Key"
                api_style = "class:api_ok"
            else:
                api_status = "✗ Sin Key"
                api_style = "class:api_fail"
        marker = " ← ACTUAL" if prov == current_provider else ""

        segments = [
            ("class:provider_name", prov),
            ("class:separator", "  ["),
            ("class:model_name", model),
            ("class:separator", "]  "),
            (api_style, api_status),
        ]
        if marker:
            segments.append(("class:current_marker", marker))

        options.append((prov, segments))

    selected = interactive_select(options, title="Selecciona un proveedor")

    if selected is None:
        console.print("[bold yellow]Cambio cancelado.[/bold yellow]")
        return False

    if selected == current_provider:
        console.print("[bold yellow]Ya estás usando ese proveedor.[/bold yellow]")
        return False

    config["provider"] = selected
    save_config(config)
    console.print(f"[bold blue]✓ Proveedor cambiado a: {selected}[/bold blue]")
    return True

# --- CAMBIO DE MODELO ---
def list_and_change_model():
    provider = config.get("provider", "gemini")
    current_model = config["providers"][provider].get("model", "")

    console.print(f"\n[bold cyan]Modelo actual ({provider}):[/bold cyan] {current_model}")
    cambiar = ask_apt_style("¿Quieres cambiar de modelo?", default="n")
    if cambiar != "s":
        return False

    if provider == "gemini":
        console.print("[bold yellow]Consultando modelos disponibles de Gemini...[/bold yellow]")
        try:
            api_key = config["providers"]["gemini"].get("api_key", "")
            if not api_key:
                console.print("[bold red]No hay API Key configurada para Gemini.[/bold red]")
                return False

            genai.configure(api_key=api_key)
            models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            options = []
            for m in models:
                model_id = m.replace("models/", "")
                segments = [("class:model_id", model_id)]
                options.append((model_id, segments))
            selected = interactive_select(options, title="Modelos Disponibles (Gemini)")

            if selected is None:
                console.print("[bold yellow]Cambio cancelado.[/bold yellow]")
                return False

            config["providers"]["gemini"]["model"] = selected
            save_config(config)
            console.print(f"[bold blue]✓ Modelo cambiado a: {selected}[/bold blue]")
            return True

        except Exception as e:
            console.print(f"[bold red]Error al listar modelos: {e}[/bold red]")
            return False

    elif provider == "openai":
        models_list = [
            ("gpt-4o", "GPT-4o", "Última y más potente"),
            ("gpt-4o-mini", "GPT-4o Mini", "Rápido y económico"),
            ("gpt-4-turbo", "GPT-4 Turbo", "Alternativa potente"),
            ("gpt-4", "GPT-4", "Potente general"),
            ("gpt-3.5-turbo", "GPT-3.5 Turbo", "Económico y rápido"),
            ("o1", "O1", "Modelo de razonamiento"),
            ("o1-mini", "O1 Mini", "Razonamiento económico"),
            ("o3-mini", "O3 Mini", "Razonamiento avanzado"),
            ("o4-mini", "O4 Mini", "Razonamiento última gen"),
        ]
        return _select_from_list(models_list, "openai")

    elif provider == "claude":
        models_list = [
            ("claude-opus-4-5-20251101", "Claude Opus 4.5", "Más potente"),
            ("claude-sonnet-4-5-20250929", "Claude Sonnet 4.5", "Balance óptimo"),
            ("claude-haiku-4-5-20241022", "Claude Haiku 4.5", "Rápido y económico"),
            ("claude-opus-4-1-20250805", "Claude Opus 4.1", "Potente alternativa"),
        ]
        return _select_from_list(models_list, "claude")

    elif provider == "mistral":
        models_list = [
            ("mistral-large-latest", "Mistral Large", "Más potente"),
            ("mistral-medium-latest", "Mistral Medium", "Balanceado"),
            ("mistral-small-latest", "Mistral Small", "Rápido y económico"),
            ("codestral-latest", "Codestral", "Escritor de código"),
            ("devstral-latest", "Devstral", "Ingeniero de software"),
            ("ministral-3b-latest", "Ministral 3B", "Súper barato y rápido, pero es tonto"),
            ("ministral-8b-latest", "Ministral 8B", "Pequeño, barato y rápido"),
            ("ministral-14b-latest", "Ministral 14B", "Bastante completo"),
        ]
        return _select_from_list(models_list, "mistral")

    elif provider == "deepseek":
        models_list = [
            ("deepseek-chat", "DeepSeek Chat", "Equilibrio general"),
            ("deepseek-reasoner", "DeepSeek Reasoner", "Razonamiento avanzado"),
        ]
        return _select_from_list(models_list, "deepseek")

    elif provider == "ollama":
        if ollama_lib is None:
            console.print("[bold red]La librería 'ollama' no está instalada. Instálala con: pip install ollama[/bold red]")
            return False

        console.print("[bold yellow]Consultando modelos locales de Ollama...[/bold yellow]")
        try:
            models_info = ollama_lib.list()
            models_list = []
            for model in models_info.get("models", []):
                name = model["name"]
                size = model.get("size", "")
                size_str = ""
                if size:
                    try:
                        size_mb = int(size) / (1024 * 1024)
                        size_str = f"{size_mb:.0f} MB"
                    except:
                        size_str = size
                models_list.append((name, name, size_str))
            if not models_list:
                console.print("[yellow]No se encontraron modelos locales. ¿Tienes alguno descargado?[/yellow]")
                return False

            return _select_from_list(models_list, "ollama", allow_custom=True)

        except Exception as e:
            console.print(f"[bold red]Error al consultar modelos de Ollama: {e}[/bold red]")
            return False

    return False

def _select_from_list(models_list, provider_name, allow_custom=False):
    options = []
    for item in models_list:
        model_id, human_name, description = item
        segments = [("class:model_id", model_id)]
        if human_name:
            segments.append(("class:separator", "  "))
            segments.append(("class:model_human", human_name))
        if description:
            segments.append(("class:separator", "  "))
            segments.append(("class:model_desc", f"({description})"))
        options.append((model_id, segments))

    if allow_custom:
        options.append(("__custom__", [("class:model_desc", "✎ Escribir manualmente...")]))

    selected = interactive_select(options, title=f"Modelos disponibles ({provider_name.capitalize()})")

    if selected is None:
        console.print("[bold yellow]Cambio cancelado.[/bold yellow]")
        return False

    if selected == "__custom__":
        choice = console.input("[bold green]Escribe el nombre exacto del modelo:[/bold green] ").strip()
        if not choice:
            console.print("[bold yellow]Cancelado.[/bold yellow]")
            return False
        selected = choice

    config["providers"][provider_name]["model"] = selected
    save_config(config)
    console.print(f"[bold blue]✓ Modelo cambiado a: {selected}[/bold blue]")
    return True

def show_help():
    help_text = """
[bold cyan]/help[/bold cyan]                Muestra esta lista de comandos.
[bold cyan]/info[/bold cyan]                Vuelve a mostrar la barra de estado (directorio, proveedor, modelo).
[bold cyan]/cmd <comando>[/bold cyan]       Ejecuta un comando bash normal sin que la IA lo vea.
[bold cyan]/preferences <txt>[/bold cyan]   Define reglas permanentes para la IA (entre comillas si lleva espacios).
[bold cyan]/auto-approve[/bold cyan]        Activa/desactiva ejecución automática de comandos.
[bold cyan]/provider[/bold cyan]            Muestra o cambia el proveedor (incluye Ollama local).
[bold cyan]/model[/bold cyan]               Muestra o cambia el modelo del proveedor actual.
[bold cyan]/api-key[/bold cyan]             Muestra o cambia tu API Key del proveedor actual.
[bold cyan]/clear[/bold cyan]               Limpia todos los mensajes del contexto.
[bold cyan]/exit[/bold cyan]                Cierra la aplicación.
    """
    console.print(Panel(help_text.strip(), title="Comandos Disponibles", border_style="green", title_align="left"))

def get_system_instruction():
    prefs = config.get("preferences", "")
    prefs_text = f"\nPreferencias específicas del usuario a seguir SIEMPRE: {prefs}" if prefs else ""

    return f"""
    Eres una IA integrada de forma TUI en la terminal del usuario.
    El directorio de trabajo actual (PWD) del usuario es: {PWD}{prefs_text}

    Tienes la capacidad de EJECUTAR COMANDOS para obtener contexto, trabajar o conversar de manera más fluida.
    
    REGLAS PARA COMANDOS:
    1. TODOS los comandos deben tener comillas balanceadas (cada ' tiene su pareja, cada " tiene su pareja)
    2. Los corchetes [] y paréntesis () deben estar balanceados
    3. Para comandos simples de una sola línea usa: [COMANDO: comando_aqui]
    4. Para comandos multilínea (sed con saltos de línea) usa: [SCRIPT: contenido]
    5. NUNCA dejes comillas sin cerrar ni corchetes sin cerrar
    
    Ejemplo CORRECTO: [COMANDO: ls -l | grep -E '^[aA]']
    Ejemplo INCORRECTO: [COMANDO: ls -l | grep -E '^[aA] (falta cerrar corchete)

    Cuando ejecutas un comando, al usuario le sale en la interfaz si aceptarlo o rechazarlo. Si la ejecución del comando falla, es porque el usuario lo rechazó.
    No ejecutes comandos sin sentido y sin parar.
    No estás haciendo un diagnóstico del sistema.
    
    La interfaz no es markdown, usa texto plano.
    No ejecutes comandos todo el rato, solo cuando lo necesites.
    No puedes usar el comando cd, tienes que hacerlo todo desde tu pwd.
    """

def init_chat_provider(provider_name):
    provider_config = config["providers"][provider_name]
    api_key = provider_config.get("api_key", "")
    model = provider_config.get("model", "")

    if provider_name == "ollama":
        if not OpenAI:
            console.print("[bold red]Error: Librería 'openai' no instalada (necesaria para Ollama). pip install openai[/bold red]")
            return None
        client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
        return {"type": "ollama", "client": client, "model": model, "history": []}

    if not api_key:
        console.print(f"[bold red]Error: No hay API Key configurada para {provider_name}.[/bold red]")
        return None

    try:
        if provider_name == "gemini":
            genai.configure(api_key=api_key)
            model_obj = genai.GenerativeModel(model_name=model, system_instruction=get_system_instruction())
            return model_obj.start_chat(history=[])

        elif provider_name == "openai":
            if not OpenAI:
                console.print("[bold red]Error: Librería 'openai' no instalada. Ejecuta: pip install openai[/bold red]")
                return None
            client = OpenAI(api_key=api_key)
            return {"type": "openai", "client": client, "model": model, "history": []}

        elif provider_name == "claude":
            if not Anthropic:
                console.print("[bold red]Error: Librería 'anthropic' no instalada. Ejecuta: pip install anthropic[/bold red]")
                return None
            client = Anthropic(api_key=api_key)
            return {"type": "claude", "client": client, "model": model, "history": []}

        elif provider_name == "mistral":
            if not Mistral:
                console.print("[bold red]Error: Librería 'mistralai' no instalada. Ejecuta: pip install mistralai[/bold red]")
                return None
            try:
                client = Mistral(api_key=api_key)
                return {"type": "mistral", "client": client, "model": model, "history": []}
            except Exception as e:
                console.print(f"[bold red]Error al inicializar Mistral: {e}[/bold red]")
                return None

        elif provider_name == "deepseek":
            if not OpenAI:
                console.print("[bold red]Error: Librería 'openai' no instalada (necesaria para DeepSeek). pip install openai[/bold red]")
                return None
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            return {"type": "deepseek", "client": client, "model": model, "history": []}

    except Exception as e:
        console.print(f"[bold red]Error al inicializar {provider_name}: {e}[/bold red]")
        return None

def send_message_to_provider(chat_obj, provider_name, message):
    try:
        if provider_name == "gemini":
            response = chat_obj.send_message(message)
            return response.text

        elif provider_name in ["openai", "deepseek", "ollama"]:
            messages = [{"role": "system", "content": get_system_instruction()}]
            messages.extend(chat_obj["history"])
            messages.append({"role": "user", "content": message})
            response = chat_obj["client"].chat.completions.create(
                model=chat_obj["model"],
                messages=messages
            )
            assistant_message = response.choices[0].message.content
            chat_obj["history"].append({"role": "user", "content": message})
            chat_obj["history"].append({"role": "assistant", "content": assistant_message})
            return assistant_message

        elif provider_name == "claude":
            chat_obj["history"].append({"role": "user", "content": message})
            response = chat_obj["client"].messages.create(
                model=chat_obj["model"],
                max_tokens=2048,
                system=get_system_instruction(),
                messages=chat_obj["history"]
            )
            assistant_message = response.content[0].text
            chat_obj["history"].append({"role": "assistant", "content": assistant_message})
            return assistant_message

        elif provider_name == "mistral":
            chat_obj["history"].append({"role": "user", "content": message})
            system_message = {"role": "system", "content": get_system_instruction()}
            response = chat_obj["client"].chat.complete(
                model=chat_obj["model"],
                messages=[system_message] + chat_obj["history"]
            )
            assistant_message = response.choices[0].message.content
            chat_obj["history"].append({"role": "assistant", "content": assistant_message})
            return assistant_message

    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        if "insufficient_quota" in error_msg.lower() or "429" in error_msg:
            return f"[bold red]⚠️ NO TIENES CRÉDITOS PARA ESTE MODELO[/bold red]\n\n[yellow]Detalles del error:[/yellow]\n{error_msg}"
        return f"[bold red]Error ({error_type}):[/bold red]\n{error_msg}"

# --- CONFIGURACIÓN INICIAL GUIADA ---
def first_run_setup():
    alguna_key = any(
        prov != "ollama" and config["providers"][prov].get("api_key")
        for prov in config["providers"]
    )
    if alguna_key:
        return False

    console.print("[bold yellow]¡Primera ejecución! Vamos a configurar tu asistente.[/bold yellow]\n")
    if ask_apt_style("¿Quieres configurar un proveedor de IA?", default='s') != 's':
        console.print("[bold red]Saliendo sin configurar...[/bold red]")
        sys.exit(0)

    providers = list(config["providers"].keys())
    options = [(p, p) for p in providers]
    selected = interactive_select(options, title="Selecciona un proveedor")

    if selected is None:
        console.print("[bold yellow]Configuración cancelada.[/bold yellow]")
        sys.exit(0)

    provider = selected
    config["provider"] = provider

    console.print(f"\n[bold cyan]Proveedor seleccionado: {provider}[/bold cyan]")
    if provider != "ollama":
        while True:
            api_key = console.input(f"[bold green]Introduce tu API Key para {provider}:[/bold green] ").strip()
            if api_key:
                config["providers"][provider]["api_key"] = api_key
                save_config(config)
                console.print("[bold blue]✓ API Key guardada.[/bold blue]")
                break
            else:
                console.print("[bold red]La API Key no puede estar vacía.[/bold red]")
    else:
        console.print("[bold blue]Ollama se ejecuta localmente, no necesita API Key.[/bold blue]")

    console.print(f"\n[bold cyan]Modelo por defecto para {provider}: {config['providers'][provider]['model']}[/bold cyan]")
    if ask_apt_style("¿Quieres cambiar el modelo?", default='n') == 's':
        list_and_change_model()

    save_config(config)
    return True

# --- MOSTRAR BARRA DE INFORMACIÓN ---
def show_header():
    provider = config.get("provider", "gemini")
    model = config["providers"][provider].get("model", "N/A")
    header = Text(f" AI Bro  |  PWD: {PWD}  |  Provider: {provider}  |  Modelo: {model} ", justify="center", style="bold cyan")
    console.print(Panel(header, expand=True, border_style="cyan"))

# --- COMPLETADOR PERSONALIZADO ---
class CommandCompleter(Completer):
    def __init__(self, commands, ignore_case=True):
        self.commands = commands
        self.ignore_case = ignore_case

    def get_completions(self, document, complete_event):
        word_before_cursor = document.get_word_before_cursor(WORD=True)
        if self.ignore_case:
            prefix = word_before_cursor.lower()
        else:
            prefix = word_before_cursor

        for cmd in self.commands:
            cmd_check = cmd.lower() if self.ignore_case else cmd
            if cmd_check.startswith(prefix):
                yield Completion(cmd, start_position=-len(word_before_cursor))

# --- MOTOR PRINCIPAL ---
def main():
    global auto_approve_commands

    os.system('clear' if os.name == 'posix' else 'cls')

    if first_run_setup():
        os.system('clear' if os.name == 'posix' else 'cls')
        console.print("[bold green]¡Configuración completada![/bold green]\n")

    show_header()
    console.print("[dim]Escribe /help para ver la lista de comandos.[/dim]\n")

    provider = config.get("provider", "gemini")
    chat = init_chat_provider(provider)
    if not chat:
        console.print("[bold red]Error: No se pudo inicializar el chat. Verifica tu configuración.[/bold red]")
        sys.exit(1)

    comandos = [
        "/help",
        "/info",
        "/cmd",
        "/preferences",
        "/auto-approve",
        "/provider",
        "/model",
        "/api-key",
        "/clear",
        "/exit"
    ]
    completer = CommandCompleter(comandos, ignore_case=True)
    session = PromptSession(completer=completer, complete_while_typing=True)

    while True:
        try:
            user_input = session.prompt(HTML('\n<ansigreen><b>❯</b></ansigreen> '))

            if user_input.strip() == "": continue

            if user_input.lower() == "/exit": break
            if user_input.lower() == "/help":
                show_help()
                continue
            if user_input.lower() == "/info":
                show_header()
                continue
            if user_input.lower() == "/clear":
                os.system('clear' if os.name == 'posix' else 'cls')
                show_header()
                continue
            if user_input.lower() == "/api-key":
                handle_api_key()
                continue
            if user_input.lower() == "/provider":
                if change_provider():
                    provider = config.get("provider", "gemini")
                    show_header()
                    chat = init_chat_provider(provider)
                    if not chat:
                        console.print("[bold red]Error: No se pudo inicializar el nuevo proveedor.[/bold red]")
                continue
            if user_input.lower() == "/model":
                if list_and_change_model():
                    provider = config.get("provider", "gemini")
                    show_header()
                    chat = init_chat_provider(provider)
                    if not chat:
                        console.print("[bold red]Error: No se pudo inicializar con el nuevo modelo.[/bold red]")
                continue
            if user_input.lower().startswith("/cmd "):
                cmd_to_run = user_input[5:].strip()
                console.print(f"[dim]Ejecutando localmente: {cmd_to_run}[/dim]")
                subprocess.run(cmd_to_run, shell=True)
                continue
            if user_input.lower().startswith("/preferences"):
                args = user_input[12:].strip()
                if not args:
                    console.print("[bold yellow]⚠️ Tienes que poner entre comillas tus preferencias después de /preferences.[/bold yellow]")
                    console.print("[dim]Ejemplo: /preferences \"Haz los commits en español\"[/dim]")
                    continue
                config["preferences"] = args
                save_config(config)
                console.print(f"[bold blue]✓ Preferencias guardadas:[/bold blue] {args}")
                provider = config.get("provider", "gemini")
                chat = init_chat_provider(provider)
                continue
            if user_input.lower() == "/auto-approve":
                auto_approve_commands = not auto_approve_commands
                config["auto_approve"] = auto_approve_commands
                save_config(config)
                status = "[bold green]ACTIVADO[/bold green]" if auto_approve_commands else "[bold red]DESACTIVADO[/bold red]"
                console.print(f"[bold cyan]Modo Auto-Approve de Comandos:[/bold cyan] {status}")
                if auto_approve_commands:
                    console.print("[yellow]⚠️ ADVERTENCIA: La IA ejecutará todos los comandos automáticamente. ¡Úsalo con cuidado![/yellow]")
                continue

            # Envío a la IA
            provider = config.get("provider", "gemini")
            with console.status("[bold cyan]Pensando...[/bold cyan]"):
                response_text = send_message_to_provider(chat, provider, user_input)

            # Procesar comandos o scripts que la IA solicite ejecutar
            while True:
                if "[COMANDO:" in response_text:
                    start_idx = response_text.find("[COMANDO:") + 9
                    end_idx = response_text.find("]", start_idx)
                    if end_idx == -1: break

                    cmd_to_run = response_text[start_idx:end_idx].strip()

                    # Si el comando es multilínea, ejecutarlo como script directamente
                    if '\n' in cmd_to_run:
                        output = execute_script(cmd_to_run)
                        feedback_msg = f"Salida del sistema para el script:\n```\n{output}\n```\nAhora responde a la petición original."
                        with console.status("[bold magenta]Analizando salida...[/bold magenta]"):
                            response_text = send_message_to_provider(chat, provider, feedback_msg)
                        continue

                    # Validar sintaxis de comando simple
                    valid, error_msg = validate_command_syntax(cmd_to_run)
                    if not valid:
                        # Intento automático de reparación pidiendo a la IA que corrija el error exacto
                        console.print(f"[yellow]⚠️ Comando con error de sintaxis: {error_msg}. Pidiendo corrección a la IA...[/yellow]")
                        fix_prompt = (
                            f"El comando que enviaste tiene un error de sintaxis de shell: {error_msg}\n"
                            f"Comando problemático: {cmd_to_run}\n"
                            "Corrige el error (cierra comillas/corchetes según sea necesario) y responde SOLO con [COMANDO: comando_corregido]"
                        )
                        with console.status("[bold magenta]Reintentando...[/bold magenta]"):
                            response_text = send_message_to_provider(chat, provider, fix_prompt)
                        # Vuelve a empezar el bucle para procesar el nuevo comando
                        continue

                    # Si el comando es sintácticamente correcto, ejecutar normalmente
                    output = execute_safely(cmd_to_run)
                    feedback_msg = f"Salida del sistema para '{cmd_to_run}':\n```\n{output}\n```\nAhora responde a la petición original."
                    with console.status("[bold magenta]Analizando salida...[/bold magenta]"):
                        response_text = send_message_to_provider(chat, provider, feedback_msg)

                elif "[SCRIPT:" in response_text:
                    start_idx = response_text.find("[SCRIPT:") + 8
                    end_idx = response_text.find("]", start_idx)
                    if end_idx == -1: break

                    script_content = response_text[start_idx:end_idx].strip()
                    output = execute_script(script_content)
                    feedback_msg = f"Salida del sistema para el script:\n```\n{output}\n```\nAhora responde a la petición original."
                    with console.status("[bold magenta]Analizando salida del script...[/bold magenta]"):
                        response_text = send_message_to_provider(chat, provider, feedback_msg)

                else:
                    break

            if "NO TIENES CRÉDITOS" in response_text:
                console.print(Panel(response_text, title=f"{provider.capitalize()} - ERROR", title_align="left", border_style="red"))
            else:
                console.print(Panel(response_text, title=f"{provider.capitalize()}", title_align="left", border_style="cyan"))

        except KeyboardInterrupt:
            continue
        except EOFError:
            break
        except Exception as e:
            console.print(f"[bold red]Error en la comunicación: {e}[/bold red]")

if __name__ == "__main__":
    main()
