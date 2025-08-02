import subprocess
import json
import time
import re
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.bar import Bar
from rich.rule import Rule
from rich.text import Text

# --- Configuration Section ---
REFRESH_RATE = 1.0  # seconds

# ** THE FIX IS HERE: SCLK and MCLK have been added back **
METRIC_KEYS = {
    "NAME": ["Device Name", "Card Series", "Card Model"],
    "TEMP": ["Temperature (Sensor junction) (C)", "Temperature (Sensor edge) (C)", "Temperature (C)"],
    "POWER_CURRENT": ["Current Socket Graphics Package Power (W)", "Average Graphics Package Power (W)"],
    "POWER_MAX": ["Max Graphics Package Power (W)"],
    "GPU_USAGE": ["GPU use (%)"],
    "VRAM_TOTAL": ["VRAM Total Memory (B)"],
    "VRAM_USED": ["VRAM Total Used Memory (B)"],
    "SCLK": ["sclk clock speed:", "sclk"],
    "MCLK": ["mclk clock speed:", "mclk"]
}

# --- Core Functions (Unchanged) ---
def get_gpu_data():
    """Fetches and merges data from --showallinfo and --showmeminfo."""
    all_data = {}
    error_log = []
    try:
        info_result = subprocess.run(
            ['rocm-smi', '--showallinfo', '--json'],
            capture_output=True, text=True, check=True, timeout=5
        )
        all_data = json.loads(info_result.stdout)
    except Exception as e:
        return {"error": f"Fatal: Could not run 'rocm-smi --showallinfo':\n{e}"}

    try:
        mem_result = subprocess.run(
            ['rocm-smi', '--showmeminfo', 'vram', '--json'],
            capture_output=True, text=True, check=True, timeout=5
        )
        mem_data = json.loads(mem_result.stdout)
        for card_id, mem_info in mem_data.items():
            if card_id in all_data:
                all_data[card_id].update(mem_info)
    except Exception as e:
        error_log.append(f"Warning: Could not get VRAM info: {e}")

    if error_log:
        all_data["error_log"] = "\n".join(error_log)
    return all_data

def get_metric(gpu_data, key_list, default=None):
    """Gets a metric from GPU data by trying a list of possible keys."""
    for key in key_list:
        if key in gpu_data:
            return gpu_data[key]
    return default

def parse_numeric_value(value_str, default=None):
    """Parses a numeric value from a string."""
    if value_str is None: return default
    if not isinstance(value_str, str): return str(value_str)
    match = re.search(r'[\d.]+', value_str)
    return match.group(0) if match else default

# --- Display Panel Creation (Unchanged from previous correct version) ---
def create_monitor_panel(all_gpu_data):
    """Creates a Rich Panel with a fully responsive and compatible layout."""
    if "error" in all_gpu_data:
        return Panel(Text(all_gpu_data["error"], justify="center"), style="bold red", title="[b]Error[/b]")

    grid = Table.grid(expand=True)
    grid.add_column()
    gpu_cards = [item for item in all_gpu_data.items() if item[0].startswith('card')]

    if not gpu_cards:
        return Panel(Text("No AMD GPUs detected by rocm-smi.", justify="center"), title="[b]AMD GPU Monitor[/b]")

    for card_id, data in gpu_cards:
        gpu_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0), expand=True)
        gpu_table.add_column("Metric", style="cyan", no_wrap=True, width=20)
        gpu_table.add_column("Value", style="green", justify="right", no_wrap=True)
        gpu_table.add_column("Bar", justify="left")

        device_name = get_metric(data, METRIC_KEYS['NAME'], card_id)
        grid.add_row(Rule(f"[bold magenta]{device_name} ({card_id})[/bold magenta]"))

        # --- Temperature ---
        temp = parse_numeric_value(get_metric(data, METRIC_KEYS['TEMP']), "N/A")
        gpu_table.add_row("Temperature", f"{temp}°C", "")

        # --- Power Usage ---
        power_curr = int(float(parse_numeric_value(get_metric(data, METRIC_KEYS['POWER_CURRENT']), "0")))
        power_max = int(float(parse_numeric_value(get_metric(data, METRIC_KEYS['POWER_MAX']), "0")))
        power_text = f"{power_curr} W / {power_max} W" if power_max > 0 else f"{power_curr} W"
        power_bar = Bar(size=power_max, begin=0, end=power_curr, width=None) if power_max > 0 else ""
        gpu_table.add_row("Power Usage", power_text, power_bar)

        # --- GPU Usage ---
        usage = int(float(parse_numeric_value(get_metric(data, METRIC_KEYS['GPU_USAGE']), '0')))
        bar_color = "green" if usage < 70 else "yellow" if usage < 90 else "red"
        gpu_table.add_row("GPU Usage", f"{usage} %", Bar(size=100, begin=0, end=usage, color=bar_color, width=None))

        # --- VRAM Usage ---
        vram_used_b = int(get_metric(data, METRIC_KEYS['VRAM_USED'], 0))
        vram_total_b = int(get_metric(data, METRIC_KEYS['VRAM_TOTAL'], 0))
        
        vram_text = "N/A"
        vram_bar = ""
        if vram_total_b > 0:
            vram_used_gb = vram_used_b / 1e9
            vram_total_gb = vram_total_b / 1e9
            vram_text = f"{vram_used_gb:.1f} GB / {vram_total_gb:.1f} GB"
            vram_bar = Bar(size=vram_total_b, begin=0, end=vram_used_b, color="cyan", width=None)
        gpu_table.add_row("VRAM Usage", vram_text, vram_bar)

        # --- Clock Speeds ---
        sclk = parse_numeric_value(get_metric(data, METRIC_KEYS['SCLK']), "N/A")
        mclk = parse_numeric_value(get_metric(data, METRIC_KEYS['MCLK']), "N/A")
        gpu_table.add_row("GPU Clock (sclk)", f"{sclk} MHz", "")
        gpu_table.add_row("Memory Clock (mclk)", f"{mclk} MHz", "")
        
        grid.add_row(gpu_table)

    return Panel(grid, title="[bold]AMD GPU Monitor[/bold]", border_style="blue")

# --- Main Loop (Unchanged) ---
def main():
    """Main function to run the GPU monitor."""
    console = Console()
    with Live(console=console, screen=False, auto_refresh=False, vertical_overflow="visible") as live:
        try:
            while True:
                all_gpu_data = get_gpu_data()
                panel = create_monitor_panel(all_gpu_data)
                live.update(panel)
                live.refresh()
                time.sleep(REFRESH_RATE)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping GPU monitor.[/yellow]")
        except Exception as e:
            console.print(f"\n[bold red]An unexpected error occurred: {type(e).__name__} - {e}[/bold red]")

if __name__ == "__main__":
    main()
