import json
import os
from datetime import datetime

from config.paths import HISTORY_DIR, ensure_output_dirs


def save_forecast_result(forecast_result):
    ensure_output_dirs()

    farm_name = (
        forecast_result["farm_name"]
        .lower()
        .replace(" ", "_")
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_path = os.path.join(
        HISTORY_DIR,
        f"{farm_name}_forecast_{timestamp}.json",
    )

    with open(output_path, "w") as file:
        json.dump(forecast_result, file, indent=4)

    return output_path