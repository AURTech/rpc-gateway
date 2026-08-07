import argparse
import os
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Create an isolated Docker environment and run the real Gateway integration flow.',
    )
    parser.add_argument('--profile', choices=('quick', 'full'), default='quick')
    parser.add_argument('--report-dir', type=Path)
    parser.add_argument('--no-build', action='store_true')
    parser.add_argument('--image-tag')
    parser.add_argument('--workers', type=int, choices=range(2, 33), default=2)
    return parser.parse_args()


def _docker_command() -> list[str]:
    direct = subprocess.run(['docker', 'info'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if direct.returncode == 0:
        return ['docker']
    elevated = subprocess.run(
        ['sudo', '-n', 'docker', 'info'],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if elevated.returncode == 0:
        preserved = ','.join(
            (
                'INTEGRATION_PROJECT_NAME',
                'INTEGRATION_IMAGE_TAG',
                'INTEGRATION_POSTGRES_PASSWORD',
                'INTEGRATION_APP_KEY',
                'INTEGRATION_ENDPOINT_KEY',
                'INTEGRATION_SESSION_SECRET',
                'INTEGRATION_RUN_TOKEN',
                'INTEGRATION_SUBNET',
                'INTEGRATION_PROFILE',
                'INTEGRATION_API_WORKERS',
                'INTEGRATION_API_A_WORKERS',
                'INTEGRATION_API_B_WORKERS',
                'INTEGRATION_REPORT_DIR',
            )
        )
        return ['sudo', '-n', f'--preserve-env={preserved}', 'docker']
    raise PermissionError('Docker daemon access requires membership in the docker group or passwordless sudo.')


def _compose_command(docker: list[str], compose_file: Path, project: str, *args: str) -> list[str]:
    return [*docker, 'compose', '-f', str(compose_file), '-p', project, *args]


def _secret() -> str:
    return secrets.token_urlsafe(32)


def main() -> None:
    args = _parse_args()
    server_root = Path(__file__).resolve().parents[2]
    compose_file = server_root / 'docker-compose.integration.yml'
    run_id = f'{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}'
    project = f'rpc-gateway-integration-{secrets.token_hex(4)}'
    report_dir = (args.report_dir or server_root.parent / '.integration-reports' / run_id).resolve()
    report_dir.mkdir(parents=True, exist_ok=False)
    report_dir.chmod(0o777)

    environment = os.environ.copy()
    environment.update(
        {
            'INTEGRATION_PROJECT_NAME': project,
            'INTEGRATION_IMAGE_TAG': args.image_tag or f'gateway-integration-{run_id.lower()}',
            'INTEGRATION_POSTGRES_PASSWORD': _secret(),
            'INTEGRATION_APP_KEY': _secret(),
            'INTEGRATION_ENDPOINT_KEY': _secret(),
            'INTEGRATION_SESSION_SECRET': _secret(),
            'INTEGRATION_RUN_TOKEN': secrets.token_urlsafe(18),
            'INTEGRATION_SUBNET': f'10.203.{secrets.randbelow(240) + 10}.0/24',
            'INTEGRATION_PROFILE': args.profile,
            'INTEGRATION_API_WORKERS': str(args.workers),
            'INTEGRATION_API_A_WORKERS': str((args.workers + 1) // 2),
            'INTEGRATION_API_B_WORKERS': str(args.workers // 2),
            'INTEGRATION_REPORT_DIR': str(report_dir),
        }
    )
    up_args = ['up', '--abort-on-container-exit', '--exit-code-from', 'runner']
    if not args.no_build:
        up_args.append('--build')
    up_args.append('runner')

    exit_code = 1
    docker: list[str] = []
    try:
        docker = _docker_command()
        try:
            result = subprocess.run(
                _compose_command(docker, compose_file, project, *up_args),
                cwd=server_root,
                env=environment,
                check=False,
                timeout=4500 if args.profile == 'full' else 2100,
            )
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            print('Gateway integration exceeded its watchdog deadline.', file=sys.stderr)
        logs = subprocess.run(
            _compose_command(docker, compose_file, project, 'logs', '--no-color'),
            cwd=server_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        (report_dir / 'compose.log').write_text(logs.stdout + logs.stderr, encoding='utf-8')
    except (FileNotFoundError, PermissionError) as exc:
        print(str(exc) or 'Docker Compose is required to run the Gateway integration flow.', file=sys.stderr)
        raise SystemExit(2) from exc
    finally:
        if docker:
            subprocess.run(
                _compose_command(docker, compose_file, project, 'down', '--volumes', '--remove-orphans'),
                cwd=server_root,
                env=environment,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        report_dir.chmod(0o700)

    print(f'Integration report: {report_dir / "report.json"}')
    print(f'Compose log: {report_dir / "compose.log"}')
    raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
