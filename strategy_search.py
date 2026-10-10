"""Chart-adaptive, family-balanced search with bounded diversity archives."""
import hashlib
import json
import math
import random
import secrets
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np


FILTER_GENES = {
    'use_ema_filter': ('ema_len',),
    'use_min_volat': ('min_width_pct',),
    'use_squeeze': ('sqz_len',),
    'use_smc': ('smc_swing_len', 'smc_mode'),
    'use_rsi': ('rsi_len', 'rsi_mode', 'rsi_ob', 'rsi_os'),
    'use_adx': ('adx_len', 'adx_threshold'),
    'use_vol': ('vol_ma_len', 'vol_mult'),
}
CORE_GENES = {
    'SuperTrend_Trend': ('st_period', 'st_mult'),
    'EMA_Cross': ('ema_len',),
    'Squeeze_Breakout': ('sqz_len',),
    'SMC_Structure': ('smc_swing_len',),
    'RSI_Reversal': ('rsi_len', 'rsi_ob', 'rsi_os'),
}
SELF_FILTER = {
    'EMA_Cross': 'use_ema_filter', 'Squeeze_Breakout': 'use_squeeze',
    'SMC_Structure': 'use_smc', 'RSI_Reversal': 'use_rsi',
}


def effective_genes(params, structure_only=False):
    """Ignore disabled/unused genes: changing those is not a new strategy."""
    family = params.get('strategy_type', 'SuperTrend_Trend')
    result = {'strategy_type': family}
    keys = set(CORE_GENES[family])
    for flag, genes in FILTER_GENES.items():
        enabled = bool(params.get(flag, False)) and flag != SELF_FILTER.get(family)
        result[flag] = enabled
        if enabled:
            keys.update(genes)
    for mode in ('tp', 'sl'):
        value = params.get(f'{mode}_mode', 'ATR')
        result[f'{mode}_mode'] = value
        if value in ('Fixed', 'Both'):
            keys.add(f'{mode}_fixed_pct')
        if value in ('ATR', 'Both'):
            keys.update(('st_period', f'{mode}_atr_mult'))
    for flag, gene in (('use_time_exit', 'max_bars_hold'), ('use_tr_exit', 'tr_ma_len')):
        result[flag] = bool(params.get(flag, True))
        if result[flag]:
            keys.add(gene)
    if not structure_only:
        result.update({key: params.get(key) for key in sorted(keys)})
    return result


def fingerprint(params, structure_only=False):
    payload = json.dumps(effective_genes(params, structure_only), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def chart_options(data, timeframe, base):
    """Estimate ranges from the training portion only; retain all families."""
    import re
    match = re.fullmatch(r'([1-9][0-9]*)([mhdwM])', timeframe)
    if not match:
        raise ValueError(f'지원하지 않는 봉 주기: {timeframe}')
    minutes = int(match[1]) * {'m': 1, 'h': 60, 'd': 1440, 'w': 10080, 'M': 43200}[match[2]]
    end = int(data['length'] * .70)
    c, h, l = (np.asarray(data[key][:end], dtype=float) for key in ('c', 'h', 'l'))
    widths = (h - l) / np.maximum(c, 1e-12) * 100
    widths = widths[np.isfinite(widths) & (widths > 0)]
    width = float(np.median(widths)) if len(widths) else .5
    scale = float(np.clip(math.sqrt(60 / minutes), .35, 3))
    options = {key: list(values) for key, values in base.items()}
    for key in ('ema_len', 'tr_ma_len', 'sqz_len', 'rsi_len', 'adx_len', 'vol_ma_len', 'st_period'):
        minimum = 20 if key == 'ema_len' else (10 if key == 'tr_ma_len' else 5)
        options[key] = sorted({max(minimum, min(600, round(value * scale))) for value in base[key]})
    options['min_width_pct'] = [round(max(.01, width * factor), 4) for factor in (.25, .5, .75, 1, 1.25)]
    options['tp_fixed_pct'] = [round(max(.2, min(200, width * factor)), 3) for factor in (2, 4, 8, 16, 32)]
    options['sl_fixed_pct'] = [round(max(.1, min(30, width * factor)), 3) for factor in (.75, 1, 1.5, 2, 3)]
    options['tp_atr_mult'] = [1.5, 2., 3., 4., 6., 8., 12.]
    options['max_bars_hold'] = sorted({max(2, min(2000, round(hours * 60 / minutes))) for hours in (6, 12, 24, 72, 168, 336)})
    return options, {'timeframe_minutes': minutes, 'training_median_range_pct': round(width, 5)}


def normalize(candidate, rng):
    own = SELF_FILTER.get(candidate['strategy_type'])
    if own:
        candidate[own] = False
    active = [flag for flag in FILTER_GENES if candidate.get(flag)]
    for flag in rng.sample(active, max(0, len(active) - 2)):
        candidate[flag] = False
    return candidate


def population(size, families, options, archives, rng):
    """Equal family budgets each generation, with 35% fresh exploration."""
    result, seen = [], set()
    order = list(families)
    rng.shuffle(order)
    for i in range(size):
        family = order[i % len(order)]
        parents = archives[family]
        for attempt in range(50):
            candidate = {key: rng.choice(values) for key, values in options.items()}
            candidate.update({flag: False for flag in FILTER_GENES})
            for flag in rng.sample(list(FILTER_GENES), rng.randrange(3)):
                candidate[flag] = True
            candidate.update(use_tr_exit=rng.choice([True, False]), use_time_exit=rng.choice([True, False]))
            if parents and rng.random() >= .35:
                p1, p2 = rng.choices(parents, k=2)
                candidate = {key: rng.choice((p1['params'][key], p2['params'][key])) for key in candidate}
                for key in rng.sample(list(options), min(4, len(options))):
                    candidate[key] = rng.choice(options[key])
                flag = rng.choice(list(FILTER_GENES) + ['use_tr_exit', 'use_time_exit'])
                candidate[flag] = not candidate[flag]
            candidate['strategy_type'] = family
            normalize(candidate, rng)
            signature = fingerprint(candidate)
            if signature not in seen:
                break
        seen.add(signature)
        result.append(candidate)
    return result


def qualifies(result, min_trades, max_mdd):
    metrics = result['sim_res']['oos']
    return (math.isfinite(result['score']) and
            all(math.isfinite(float(metrics[key])) for key in ('trades_count', 'mdd', 'return_pct', 'sharpe', 'win_rate')) and
            metrics['trades_count'] >= min_trades and
            abs(metrics['mdd']) <= max_mdd and metrics['return_pct'] > 0)


def select_result(candidates, history, symbol, timeframe, rng):
    """Prefer unseen structures within 15%/15 points of the best fitness."""
    best = max(candidates, key=lambda item: item['score'])
    floor = best['score'] - max(15., abs(best['score']) * .15)
    pool = [item for item in candidates if item['score'] >= floor]
    previous = [record for record in history
                if isinstance(record, dict) and isinstance(record.get('best_params'), dict)
                and record['best_params'].get('strategy_type', 'SuperTrend_Trend') in CORE_GENES]
    exact = {fingerprint(record['best_params']) for record in previous}
    fresh = [item for item in pool if fingerprint(item['params']) not in exact]
    if fresh:
        pool = fresh
    structures = {fingerprint(record['best_params'], True) for record in previous}
    new_structures = [item for item in pool if fingerprint(item['params'], True) not in structures]
    if new_structures:
        pool = new_structures
    family_counts = {}
    for record in previous:
        family = record['best_params'].get('strategy_type')
        weight = 3 if (record.get('symbol'), record.get('timeframe')) == (symbol, timeframe) else 1
        family_counts[family] = family_counts.get(family, 0) + weight
    # Choose family first, so one family with many close candidates cannot dominate.
    families = sorted({item['params']['strategy_type'] for item in pool})
    chosen_family = rng.choices(families, weights=[1 / (1 + family_counts.get(f, 0)) ** 2 for f in families])[0]
    chosen = rng.choice([item for item in pool if item['params']['strategy_type'] == chosen_family])
    return chosen, {
        'selection': 'fresh_structure' if new_structures else ('fresh_parameters' if fresh else 'quality_fallback'),
        'quality_pool_size': len(pool), 'best_fitness': best['score'], 'selected_fitness': chosen['score'],
        'fingerprint': fingerprint(chosen['params']),
    }


def run_search(df, symbol, timeframe, max_iterations, min_trades, max_mdd,
               num_workers, progress_callback, cancel_check, recent_history=None, seed=None):
    # Local import keeps the Pine exporter independent of the search module.
    from ai_generator import GENE_OPTIONS, STRATEGY_ARCHETYPES, _worker_simulate, generate_pine_script_v6
    from quant_engine import precompute_df_arrays, run_simulation
    import os

    if max_iterations < 1:
        raise ValueError('탐색 횟수는 1 이상이어야 합니다.')
    started = time.time()
    seed = secrets.randbits(64) if seed is None else seed
    rng = random.Random(seed)
    data = df if isinstance(df, dict) else precompute_df_arrays(df)
    if data['length'] < 100:
        raise ValueError('전략 생성에 최소 100개 캔들이 필요합니다.')
    options, profile = chart_options(data, timeframe, GENE_OPTIONS)
    workers = min(max(num_workers or (os.cpu_count() or 1), 1), 16)
    pop_size = min(max_iterations, min(max(max_iterations // 10, 20), 1000))
    generations = math.ceil(max_iterations / pop_size)
    archives = {family: [] for family in STRATEGY_ARCHETYPES}
    valid_archives = {family: [] for family in STRATEGY_ARCHETYPES}
    counts = {family: 0 for family in STRATEGY_ARCHETYPES}
    best, completed, last_callback = None, 0, 0.

    def check_cancel():
        if cancel_check and cancel_check():
            raise RuntimeError('사용자에 의해 전략 생성이 중단되었습니다.')

    def retain(archive, item):
        if '_fingerprint' not in item:
            item['_fingerprint'] = fingerprint(item['params'])
            item['_structure'] = fingerprint(item['params'], True)
        signature = item['_fingerprint']
        if any(old['_fingerprint'] == signature for old in archive):
            return
        if len(archive) >= 24 and item['score'] < min(old['score'] for old in archive):
            return
        archive.append(item)
        archive.sort(key=lambda result: (-result['score'], result['_fingerprint']))
        # Reserve different filter/exit structures before filling with variants.
        unique, remainder, structures = [], [], set()
        for result in archive:
            structure = result['_structure']
            if structure not in structures:
                unique.append(result)
                structures.add(structure)
            else:
                remainder.append(result)
        archive[:] = (unique[:16] + remainder)[:24]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for generation in range(1, generations + 1):
            check_cancel()
            candidates = population(min(pop_size, max_iterations - completed), list(archives), options, archives, rng)
            tasks = [(data, candidate, min_trades, max_mdd) for candidate in candidates]
            # Ordered collection makes an explicit seed reproducible across worker counts.
            for result in executor.map(_worker_simulate, tasks):
                check_cancel()
                completed += 1
                family = result['params']['strategy_type']
                counts[family] += 1
                if math.isfinite(result['score']):
                    retain(archives[family], result)
                    if qualifies(result, min_trades, max_mdd):
                        retain(valid_archives[family], result)
                    if best is None or result['score'] > best['score']:
                        best = result
                now = time.time()
                if best and progress_callback and (now - last_callback > .2 or completed == max_iterations):
                    last_callback = now
                    metrics = best['sim_res']['oos']
                    progress_callback(min(99, int(completed / max_iterations * 100)),
                        f"[AI 유전 진화 {generation}/{generations}세대] {completed}/{max_iterations} 검증 "
                        f"(최고 수익률: {metrics['return_pct']:+.1f}%, 승률: {metrics['win_rate']:.1f}%, "
                        f"MDD: {metrics['mdd']:.1f}%, 거래: {metrics['trades_count']}회)")
    check_cancel()
    eligible = [item for archive in valid_archives.values() for item in archive]
    if not eligible:
        raise RuntimeError('거래 수·최대 MDD·양의 수익률 조건을 만족하는 전략을 찾지 못했습니다. 탐색 횟수나 조건을 조정해 주세요.')
    selected, diagnostics = select_result(eligible, recent_history or [], symbol, timeframe, rng)
    params = selected['params']
    simulation = run_simulation(df, params, split_ratio=.70, fast_mode=False)
    check_cancel()
    family = params['strategy_type']
    meta = STRATEGY_ARCHETYPES[family]
    summary = {'symbol': symbol, 'timeframe': timeframe, 'strategy_type': family,
               'strategy_type_kr': meta['name_kr'], 'strategy_icon': meta['icon'], 'strategy_desc': meta['desc'],
               'is_sharpe': simulation['is']['sharpe'], 'overfitting_ratio': simulation['overfitting_ratio']}
    for target, source in [('sharpe', 'sharpe'), ('return', 'return_pct'), ('mdd', 'mdd'), ('win_rate', 'win_rate'), ('trades', 'trades_count')]:
        summary[f'oos_{target}'] = simulation['oos'][source]
    diagnostics.update(seed=seed, chart_profile=profile, evaluated_by_type=counts)
    elapsed = round(time.time() - started, 2)
    summary.update(workers_used=workers, generations=generations, elapsed_time_sec=elapsed)
    title = f"AI [{meta['icon']} {family}] {symbol.replace('/', '')} {timeframe} Strategy v6"
    return {'best_params': params, 'best_sim': simulation, 'summary': summary,
            'pine_code': generate_pine_script_v6(title, params, summary),
            'strategy_type': family, 'strategy_type_kr': meta['name_kr'], 'strategy_icon': meta['icon'],
            'total_evaluated': completed, 'workers_used': workers, 'generations': generations,
            'elapsed_time_sec': elapsed, 'search_diagnostics': diagnostics}
