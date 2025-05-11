def unique_id_from_entry_data(data: dict) -> str:
    return " ".join(sorted(data["vehicles"].keys())).lower()


def vins_from_entry_data(data: dict) -> str:
    return " ".join(sorted([vehicle["vin"] for vehicle in data["vehicles"].values()]))
