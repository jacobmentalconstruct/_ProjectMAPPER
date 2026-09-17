import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.app import APP_VERSION, VENDOR_EXPORT_ROOT_NAME, create_vendor_export  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a blank-slate ProjectMapper vendor export folder and zip."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / VENDOR_EXPORT_ROOT_NAME,
        help="Directory that will receive the generated export folder and zip.",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Create only the export folder, without a zip archive.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = create_vendor_export(
        source_root=PROJECT_ROOT,
        export_root=args.output_dir,
        make_zip=not args.no_zip,
        log_callback=print,
    )
    print(f"ProjectMapper {APP_VERSION} blank-slate vendor export created.")
    print(f"Folder: {result['export_dir']}")
    if result.get("zip_path"):
        print(f"Zip: {result['zip_path']}")
    print(f"Included files: {result['included_count']}")
    print(f"Skipped entries: {result['skipped_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
