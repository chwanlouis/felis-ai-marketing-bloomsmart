import csv
import uuid
from typing import List, Dict, Any


def force_replace_product_ids(input_csv_path: str, output_csv_path: str) -> None:
    """
    Reads a CSV file, overwrites the product_id/id column for every row with a new UUID,
    and saves the modified dataset to output_csv_path.
    """
    products: List[Dict[str, Any]] = []

    with open(input_csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])

        # Determine target primary key field name
        if "product_id" in fieldnames:
            id_field = "product_id"
        elif "id" in fieldnames:
            id_field = "id"
        else:
            id_field = "product_id"
            fieldnames.insert(0, id_field)

        for row in reader:
            # Force replace existing ID with a fresh UUID
            new_id = str(uuid.uuid4())
            row[id_field] = new_id

            # If the schema uses both 'id' and 'product_id', synchronize both
            if "id" in row:
                row["id"] = new_id
            if "product_id" in row:
                row["product_id"] = new_id

            products.append(row)

    # check column unit
    other_unit = set()

    for row in products:
        unit = row.get("unit", "").strip()
        if unit not in ['磅', '公斤', '盒', '包', '支', '張', '隻']:
            other_unit.add(unit)

    if other_unit:
        print(f"⚠️ Warning: Found unexpected units: {other_unit}")

    # map units to standard units
    unit_mapping = {
        'pack': '包', 'lb': '磅', 'each': '隻'
    }
    products = [
        {**row, "unit": unit_mapping.get(row.get("unit", "").strip(), row.get("unit", "").strip())}
        for row in products
    ]

    # add column marketing_strategy if not exists
    if "marketing_strategy" not in fieldnames:
        fieldnames.append("marketing_strategy")
        for row in products:
            row["marketing_strategy"] = ""

    # Write out the updated CSV file
    with open(output_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)

    print(f"✅ Successfully force-replaced {id_field} for {len(products)} items with new UUIDs.")


if __name__ == "__main__":
    force_replace_product_ids("products-bulk-insert.csv", "products-bulk-insert-uuid.csv")