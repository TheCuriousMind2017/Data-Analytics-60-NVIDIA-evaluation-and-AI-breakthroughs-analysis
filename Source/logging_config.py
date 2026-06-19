# logging_config.py
import logging
from datetime import datetime
import os

log_filename = f"Logs/pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

os.makedirs("Logs", exist_ok=True)

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(levelname)s - %(message)s")
console.setFormatter(formatter)
logging.getLogger().addHandler(console)
