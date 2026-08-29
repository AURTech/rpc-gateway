import asyncio
import json
import os
import sys
from pathlib import Path

from scripts.gateway_flow_integration.scenario import execute_flow


def _required(name: str) -> str:
    value = os.environ.get(name, '').strip()
    if not value:
        raise ValueError(f'{name} is required.')
    return value


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        async with asyncio.timeout(10):
            await process.wait()
    except TimeoutError:
        process.kill()
        await process.wait()


async def _stress(command: list[str], *, timeout_seconds: float) -> tuple[dict[str, object], bool]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(timeout_seconds):
            stdout, stderr = await process.communicate()
    except TimeoutError:
        await _stop_process(process)
        return {'success': False, 'timed_out': True, 'timeout_seconds': timeout_seconds}, False
    text = stdout.decode(errors='replace').strip()
    error_text = stderr.decode(errors='replace').strip()
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        decoded = {'success': False, 'stdout': text[-2000:], 'stderr': error_text[-2000:]}
    payload: dict[str, object]
    if isinstance(decoded, dict):
        payload = {str(key): value for key, value in decoded.items()}
    else:
        payload = {'success': False, 'result': decoded}
    if error_text:
        payload['stderr'] = error_text[-2000:]
    return payload, process.returncode == 0 and payload.get('success') is True


async def _execute() -> tuple[dict[str, object], bool]:
    profile = os.environ.get('INTEGRATION_PROFILE', 'quick')
    workers = int(_required('INTEGRATION_API_WORKERS'))
    api_a_workers = int(_required('INTEGRATION_API_A_WORKERS'))
    api_b_workers = int(_required('INTEGRATION_API_B_WORKERS'))
    if api_a_workers + api_b_workers != workers:
        raise ValueError('API replica worker counts do not match the requested total.')
    report: dict[str, object] = {
        'profile': profile,
        'api_workers': workers,
        'api_replicas': 2,
        'api_workers_by_replica': {'api-a': api_a_workers, 'api-b': api_b_workers},
        'success': False,
        'errors': [],
    }
    success = True
    try:
        async with asyncio.timeout(600):
            e2e_report = await execute_flow(
                api_url=_required('INTEGRATION_API_URL'),
                peer_api_url=_required('INTEGRATION_PEER_API_URL'),
                mock_url=_required('INTEGRATION_MOCK_URL'),
                redis_url=_required('INTEGRATION_REDIS_URL'),
                postgres_url=_required('INTEGRATION_POSTGRES_URL'),
                token=_required('INTEGRATION_RUN_TOKEN'),
            )
            report['e2e'] = e2e_report
            if e2e_report.get('success') is not True:
                raise RuntimeError('E2E report did not contain an explicit success result.')
    except Exception as exc:
        success = False
        errors = report['errors']
        if isinstance(errors, list):
            errors.append(f'E2E: {type(exc).__name__}: {exc}')
    if not success:
        skipped = {'success': False, 'skipped': 'E2E failed; stress isolation would no longer be valid.'}
        report['runtime_state_stress'] = skipped
        report['system_cache_stress'] = skipped
        return report, False

    stress_timeout = 1800 if profile == 'full' else 600
    runtime_report, runtime_ok = await _stress(
        [
            sys.executable,
            '-m',
            'scripts.runtime_state_stress',
            '--profile',
            profile,
            '--redis-url',
            _required('RUNTIME_STATE_STRESS_REDIS_URL'),
        ],
        timeout_seconds=stress_timeout,
    )
    report['runtime_state_stress'] = runtime_report
    success = success and runtime_ok
    if not runtime_ok:
        errors = report['errors']
        if isinstance(errors, list):
            errors.append('Runtime State stress failed.')

    cache_report, cache_ok = await _stress(
        [
            sys.executable,
            '-m',
            'scripts.system_cache_stress',
            '--mode',
            'all',
            '--profile',
            profile,
            '--redis-url',
            _required('SYSTEM_CACHE_STRESS_REDIS_URL'),
            '--postgres-url',
            _required('SYSTEM_CACHE_STRESS_POSTGRES_URL'),
        ],
        timeout_seconds=stress_timeout,
    )
    report['system_cache_stress'] = cache_report
    success = success and cache_ok
    if not cache_ok:
        errors = report['errors']
        if isinstance(errors, list):
            errors.append('System Cache stress failed.')
    report['success'] = success
    return report, success


def main() -> None:
    report_file = Path(_required('INTEGRATION_REPORT_FILE'))
    try:
        report, success = asyncio.run(_execute())
    except Exception as exc:
        report = {'success': False, 'errors': [f'{type(exc).__name__}: {exc}']}
        success = False
    report_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps(report, indent=2, sort_keys=True))
    if not success:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
