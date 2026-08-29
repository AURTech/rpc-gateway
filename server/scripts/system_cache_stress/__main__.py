from scripts.system_cache_stress.cli import parse_args


def main() -> None:
    args = parse_args()
    # Reason: argparse help must work without loading application settings or database modules.
    from scripts.system_cache_stress.runner import run_stress

    run_stress(args)


if __name__ == '__main__':
    main()
