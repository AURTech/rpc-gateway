from scripts.runtime_state_stress.cli import parse_args


def main() -> None:
    args = parse_args()
    # Reason: allow argparse help to run without loading application secrets or Redis modules.
    from scripts.runtime_state_stress.runner import run_stress

    run_stress(args)


if __name__ == '__main__':
    main()
