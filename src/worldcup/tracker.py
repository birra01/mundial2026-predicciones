"""
tracker.py — Sistema de aprendizaje para el motor de apuestas.

Registra predicciones antes del partido, resultados después,
calcula ROI por mercado, calibración de probabilidades,
y ajusta los pesos del motor automáticamente.

Uso:
  1. Antes del partido:   tracker.log_prediction(match, predictions)
  2. Después del partido: tracker.log_result(match, real_stats)
  3. Para recalibrar:     tracker.recalibrate()
  4. Para ver stats:      tracker.get_report()
"""

import json
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent.parent / "data"
LEARNING_DIR = DATA_DIR / "learning"
PREDICTIONS_FILE = LEARNING_DIR / "predictions_log.json"
RESULTS_FILE = LEARNING_DIR / "results_log.json"
CALIBRATION_FILE = LEARNING_DIR / "calibration.json"
WEIGHTS_FILE = LEARNING_DIR / "learned_weights.json"

# Mercados que evaluamos (cada uno es una "apuesta" independiente)
MARKET_TYPES = {
    'goals_over': {'label': 'Goles Over', 'icon': '⚽'},
    'goals_under': {'label': 'Goles Under', 'icon': '🛡️'},
    'cards_over': {'label': 'Tarjetas Over', 'icon': '🟨'},
    'cards_under': {'label': 'Tarjetas Under', 'icon': '🟩'},
    'corners_over': {'label': 'Córners Over', 'icon': '🏳️'},
    'corners_under': {'label': 'Córners Under', 'icon': '🏁'},
    '1x2_home': {'label': '1X2 Local', 'icon': '🏠'},
    '1x2_draw': {'label': '1X2 Empate', 'icon': '🤝'},
    '1x2_away': {'label': '1X2 Visitante', 'icon': '✈️'},
    'shots_over': {'label': 'Tiros Over', 'icon': '🎯'},
    'shots_under': {'label': 'Tiros Under', 'icon': '🚫'},
    'fouls_over': {'label': 'Faltas Over', 'icon': '⚡'},
    'fouls_under': {'label': 'Faltas Under', 'icon': '🔇'},
}


def _ensure_dir():
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path, default=None):
    if default is None:
        default = {}
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def _save_json(path, data):
    _ensure_dir()
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def classify_market(stat_key, direction, line):
    """Clasifica una apuesta en un tipo de mercado legible."""
    stat_map = {
        'totalShotsOnGoal': 'shots',
        'shotsOnGoal': 'shots',
        'cornerKicks': 'corners',
        'yellowCards': 'cards',
        'fouls': 'fouls',
    }
    base = stat_map.get(stat_key, stat_key)
    if stat_key == 'totalGoals' or stat_key == 'goals':
        base = 'goals'
    return f"{base}_{direction}"


class BetTracker:
    """Sistema de tracking y aprendizaje de apuestas."""

    def __init__(self):
        self.predictions = _load_json(PREDICTIONS_FILE, [])
        self.results = _load_json(RESULTS_FILE, [])
        self.calibration = _load_json(CALIBRATION_FILE, {})
        self.learned_weights = _load_json(WEIGHTS_FILE, {})

    # ─── REGISTRAR PREDICCIÓN (antes del partido) ────────────

    def log_prediction(self, match_name, home_team, away_team, value_bets_list, match_date=None):
        """Registra las predicciones para un partido antes de que se juegue.

        Args:
            match_name: "Team A vs Team B"
            home_team, away_team: nombres
            value_bets_list: lista de dicts de value_bets (de build_value_bets)
            match_date: string ISO o None (usa now)
        """
        # Deduplicación: no registrar si ya existe predicción para este partido
        match_lower = match_name.lower().strip()
        # Resolver aliases para comparación
        match_normalized = match_lower.replace('españa', 'spain').replace('bélgica', 'belgium')
        for existing in self.predictions:
            existing_name = existing.get('match', '').lower().strip()
            existing_normalized = existing_name.replace('españa', 'spain').replace('bélgica', 'belgium')
            if existing_normalized == match_normalized:
                return len(existing.get('bets', []))  # ya registrado
        
        if match_date is None:
            match_date = datetime.now().isoformat()

        entry = {
            'match': match_name,
            'home': home_team,
            'away': away_team,
            'date': match_date,
            'logged_at': datetime.now().isoformat(),
            'bets': []
        }

        for vb in value_bets_list:
            stat_key = vb.get('stat_key', '')
            line = vb.get('line', 0)
            prob = vb.get('prob_over', 0) / 100.0
            odd = vb.get('odd')
            edge = vb.get('edge_pct', 0)

            # Determinar dirección y mercado
            direction = vb.get('direction', 'over')  # usar direction del bridge si existe
            # Fallback: si no hay direction, inferir de prob
            if 'direction' not in vb and odd and prob < 0.5:
                direction = 'under'
                prob = 1.0 - prob  # invertir para la prob de under
                if odd > 1:
                    # Recalcular edge para under
                    implied = 1.0 / odd if odd > 0 else 0
                    edge = round((prob - implied) * 100, 1)

            market = classify_market(stat_key, direction, line)

            entry['bets'].append({
                'stat_key': stat_key,
                'line': line,
                'direction': direction,
                'market': market,
                'total_pred': vb.get('total_pred', 0),
                'prob': round(prob, 4),
                'odd': odd,
                'edge_pct': edge,
                'ev_pct': vb.get('ev_pct'),
                'result': None,  # se llena después
                'actual_value': None,
            })

        self.predictions.append(entry)
        _save_json(PREDICTIONS_FILE, self.predictions)
        return len(entry['bets'])

    # ─── REGISTRAR RESULTADO (después del partido) ──────────

    def log_result(self, match_name, real_stats, home_score=None, away_score=None):
        """Registra el resultado real de un partido y evalúa las apuestas.

        Args:
            match_name: "Team A vs Team B"
            real_stats: dict con {stat_key: {total, home, away}} — de sofascore
            home_score, away_score: goles finales
        """
        # Deduplicación: no registrar si ya existe resultado para este partido
        match_lower = match_name.lower().strip()
        match_normalized = match_lower.replace('españa', 'spain').replace('bélgica', 'belgium')
        for existing in self.results:
            existing_name = existing.get('match', '').lower().strip()
            existing_normalized = existing_name.replace('españa', 'spain').replace('bélgica', 'belgium')
            if existing_normalized == match_normalized:
                return len(existing.get('bet_results', []))  # ya registrado
        
        result_entry = {
            'match': match_name,
            'date': datetime.now().isoformat(),
            'home_score': home_score,
            'away_score': away_score,
            'stats': real_stats,
            'bet_results': []
        }

        # Encontrar la predicción correspondiente
        pred = None
        for p in reversed(self.predictions):  # más reciente primero
            if p['match'].lower().strip() == match_name.lower().strip():
                pred = p
                break

        if not pred:
            # Sin predicción previa, solo guardar stats reales
            self.results.append(result_entry)
            _save_json(RESULTS_FILE, self.results)
            return 0

        evaluated = 0
        for bet in pred['bets']:
            stat_key = bet['stat_key']
            line = bet['line']
            direction = bet['direction']
            prob = bet['prob']
            odd = bet['odd']

            # Obtener valor real
            # Para goles usar marcador real, no xG
            if stat_key == 'totalGoals' and home_score is not None and away_score is not None:
                actual = home_score + away_score
            else:
                real = real_stats.get(stat_key, {})
                actual = real.get('total')
            if actual is None:
                continue

            # Determinar si ganó
            if direction == 'over':
                won = actual > line
            else:
                won = actual <= line

            # Calcular payout
            stake = 1.0  # unit stake
            payout = stake * odd if (won and odd) else 0
            profit = payout - stake if won else -stake

            bet_result = {
                'market': bet['market'],
                'stat_key': stat_key,
                'line': line,
                'direction': direction,
                'prob': prob,
                'odd': odd,
                'edge_pct': bet['edge_pct'],
                'actual_value': actual,
                'won': won,
                'profit': round(profit, 2),
                'payout': round(payout, 2),
            }
            result_entry['bet_results'].append(bet_result)
            evaluated += 1

            # Actualizar la predicción original
            bet['result'] = 'won' if won else 'lost'
            bet['actual_value'] = actual

        self.results.append(result_entry)
        _save_json(PREDICTIONS_FILE, self.predictions)
        _save_json(RESULTS_FILE, self.results)
        return evaluated

    # ─── MÉTRICAS ────────────────────────────────────────────

    def get_market_stats(self):
        """Calcula ROI y win rate por tipo de mercado."""
        market_data = defaultdict(lambda: {
            'bets': 0, 'wins': 0, 'losses': 0,
            'total_staked': 0, 'total_profit': 0,
            'probs': [], 'outcomes': [],  # para calibración
        })

        for result in self.results:
            for br in result.get('bet_results', []):
                market = br['market']
                d = market_data[market]
                d['bets'] += 1
                d['total_staked'] += 1.0
                if br['won']:
                    d['wins'] += 1
                    d['total_profit'] += br['profit']
                else:
                    d['losses'] += 1
                    d['total_profit'] -= 1.0
                d['probs'].append(br['prob'])
                d['outcomes'].append(1 if br['won'] else 0)

        # Calcular métricas
        stats = {}
        for market, d in market_data.items():
            bets = d['bets']
            if bets == 0:
                continue
            stats[market] = {
                'bets': bets,
                'wins': d['wins'],
                'losses': d['losses'],
                'win_rate': round(d['wins'] / bets * 100, 1),
                'roi': round(d['total_profit'] / d['total_staked'] * 100, 1),
                'total_profit': round(d['total_profit'], 2),
                'avg_prob': round(sum(d['probs']) / len(d['probs']) * 100, 1),
                'calibration_error': self._calibration_error(d['probs'], d['outcomes']),
            }
        return stats

    def _calibration_error(self, probs, outcomes):
        """Calibration error: si decimos 70%, ¿gana el 70% de las veces?"""
        if len(probs) < 3:
            return None  # pocos datos

        # Agrupar en bins de 10%
        bins = defaultdict(lambda: {'pred': [], 'actual': []})
        for p, o in zip(probs, outcomes):
            bin_key = int(p * 10) / 10.0  # 0.0, 0.1, 0.2, ...
            bins[bin_key]['pred'].append(p)
            bins[bin_key]['actual'].append(o)

        total_error = 0
        total_count = 0
        for bin_key, data in bins.items():
            n = len(data['pred'])
            if n < 2:
                continue
            avg_pred = sum(data['pred']) / n
            avg_actual = sum(data['actual']) / n
            total_error += abs(avg_pred - avg_actual) * n
            total_count += n

        return round(total_error / total_count * 100, 1) if total_count > 0 else None

    def get_overall_stats(self):
        """Estadísticas generales del tracker."""
        total_bets = 0
        total_wins = 0
        total_profit = 0
        total_staked = 0

        for result in self.results:
            for br in result.get('bet_results', []):
                total_bets += 1
                total_staked += 1.0
                if br['won']:
                    total_wins += 1
                    total_profit += br['profit']
                else:
                    total_profit -= 1.0

        return {
            'total_matches': len(self.results),
            'total_predictions': len(self.predictions),
            'total_bets': total_bets,
            'total_wins': total_wins,
            'win_rate': round(total_wins / total_bets * 100, 1) if total_bets > 0 else 0,
            'roi': round(total_profit / total_staked * 100, 1) if total_staked > 0 else 0,
            'total_profit': round(total_profit, 2),
        }

    def get_best_worst_markets(self):
        """Devuelve los mejores y peores mercados por ROI."""
        stats = self.get_market_stats()
        if not stats:
            return None, None

        sorted_markets = sorted(stats.items(), key=lambda x: x[1]['roi'], reverse=True)
        best = sorted_markets[:3]
        worst = sorted_markets[-3:]
        return best, worst

    # ─── RECALIBRACIÓN ──────────────────────────────────────

    def recalibrate(self):
        """Analiza el historial y sugiere ajustes a los pesos del motor.

        Returns: dict con ajustes sugeridos y métricas.
        """
        market_stats = self.get_market_stats()
        if not market_stats or sum(d['bets'] for d in market_stats.values()) < 10:
            return {'status': 'insufficient_data', 'min_bets_needed': 10}

        adjustments = {
            'timestamp': datetime.now().isoformat(),
            'market_performance': market_stats,
            'weight_adjustments': {},
            'recommendations': [],
        }

        # Analizar qué mercados funcionan mejor
        for market, stats in market_stats.items():
            if stats['bets'] < 5:
                continue

            roi = stats['roi']
            win_rate = stats['win_rate']
            cal_error = stats.get('calibration_error')

            if roi > 10:
                adjustments['recommendations'].append({
                    'market': market,
                    'action': 'increase_weight',
                    'reason': f"ROI +{roi}%, win rate {win_rate}%",
                    'suggested_weight': min(1.5, 1.0 + roi / 50),
                })
            elif roi < -15:
                adjustments['recommendations'].append({
                    'market': market,
                    'action': 'decrease_weight',
                    'reason': f"ROI {roi}%, win rate {win_rate}%",
                    'suggested_weight': max(0.3, 1.0 + roi / 50),
                })

            if cal_error and cal_error > 15:
                adjustments['recommendations'].append({
                    'market': market,
                    'action': 'recalibrate_probabilities',
                    'reason': f"Calibration error {cal_error}% — probabilities are unreliable",
                })

        # Guardar ajustes aprendidos
        for rec in adjustments['recommendations']:
            if rec['action'] in ('increase_weight', 'decrease_weight'):
                adjustments['weight_adjustments'][rec['market']] = rec['suggested_weight']

        self.learned_weights = adjustments
        _save_json(CALIBRATION_FILE, adjustments)
        _save_json(WEIGHTS_FILE, adjustments['weight_adjustments'])

        return adjustments

    def get_market_weight(self, market):
        """Devuelve el peso aprendido para un mercado (default 1.0)."""
        return self.learned_weights.get(market, 1.0)

    # ─── REPORTE ────────────────────────────────────────────

    def get_report(self):
        """Genera un reporte completo del estado del tracker."""
        overall = self.get_overall_stats()
        market_stats = self.get_market_stats()
        best, worst = self.get_best_worst_markets()
        calibration = _load_json(CALIBRATION_FILE, {})

        return {
            'overall': overall,
            'by_market': market_stats,
            'best_markets': best,
            'worst_markets': worst,
            'calibration': calibration,
            'learned_weights': self.learned_weights,
        }

    # ─── BACKFILL: registrar partidos ya jugados ────────────

    def backfill_from_existing(self, predictions_data, real_stats_data):
        """Carga predicciones y resultados de archivos existentes
        para entrenar el sistema con datos históricos.

        predictions_data: lista de dicts con predicciones pasadas
        real_stats_data: dict de real_stats.json
        """
        imported = 0
        for match_key, real in real_stats_data.items():
            if match_key.startswith('_'):
                continue
            if real.get('_blocked'):
                continue

            # Parsear nombre del partido
            parts = match_key.split(' vs ')
            if len(parts) != 2:
                continue
            home, away = parts[0].strip(), parts[1].strip()

            # Buscar predicción correspondiente
            pred = None
            for p in predictions_data:
                ph = p.get('home_team', '').lower().strip()
                pa = p.get('away_team', '').lower().strip()
                if (ph == home.lower() and pa == away.lower()) or \
                   (ph == away.lower() and pa == home.lower()):
                    pred = p
                    break

            if not pred:
                continue

            # Extraer value bets si existen
            vb_list = pred.get('value_bets', [])
            if not vb_list:
                continue

            # Registrar predicción
            self.log_prediction(
                f"{home} vs {away}", home, away, vb_list,
                match_date=pred.get('date')
            )

            # Registrar resultado
            stats_for_result = {}
            for sk in ['cornerKicks', 'yellowCards', 'totalShotsOnGoal',
                        'shotsOnGoal', 'fouls', 'totalGoals']:
                if sk in real:
                    stats_for_result[sk] = real[sk]

            gs = real.get('home_score')
            as_ = real.get('away_score')
            self.log_result(
                f"{home} vs {away}", stats_for_result,
                home_score=gs, away_score=as_
            )
            imported += 1

        return imported


# ─── FUNCIÓN DE CONVENIENCIA ──────────────────────────────

def get_tracker():
    """Obtener instancia singleton del tracker."""
    return BetTracker()
