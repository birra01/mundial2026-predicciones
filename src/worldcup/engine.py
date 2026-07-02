"""
World Cup 2026 Prediction Engine v2
Estadisticas AJUSTADAS POR RIVAL — cada stat se normaliza contra lo que permite/concede el oponente
"""
import json, os, math
from pathlib import Path
from collections import defaultdict

# ---------- CONSTANTES ----------
WEIGHTS = {
    'expectedGoals': 2.5, 'bigChanceCreated': 1.5,
    'totalShotsOnGoal': 1.2, 'shotsOnTarget': 1.8,
    'ballPossession': 0.8, 'cornerKicks': 0.6,
    'passes': 0.4, 'touchesInPenaltyArea': 1.0,
    'finalThirdEntries': 0.7, 'crosses': 0.5,
    'goalkeeperSaves': -0.5, 'fouls': -0.3,
    'yellowCards': -0.4, 'errorsLeadToGoal': -2.0,
}

# Parámetros del modelo (tuneables, se sobreescriben en __init__)
HOME_ADV = 0.10
ELO_K = 32
ELO_HOME = 30
DRAW_MARGIN = 35       # margen Elo para empate (a mayor, más draws)
STAT_DRAW_PEAK = 0.35  # draw máximo del modelo estadístico
STAT_DRAW_WIDTH = 4.5  # anchura de la campana de draw

# Pesos de mezcla (deben sumar ~1.0)
W_ELO = 0.25
W_STATS = 0.25
W_POISSON = 0.25
W_FORM = 0.25

class WorldCupEngine:
    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / "data" / "worldcup"
        self.data_dir = Path(data_dir)
        self.matches = []
        self.team_stats = {}
        self.elo = {}
        self.team_matches = defaultdict(list)
        # NUEVO: promedios de lo que CADA EQUIPO PERMITE al rival (defensiva)
        self.team_allows = defaultdict(lambda: defaultdict(list))

    # ─── CARGA ─────────────────────────────────────────
    def load_data(self):
        json_path = self.data_dir / "all_matches.json"
        if not json_path.exists():
            raise FileNotFoundError(f"No encontrado: {json_path}")
        with open(json_path) as f:
            self.matches = json.load(f)
        self._compute_team_stats()
        self._compute_elo()
        print(f"Cargados {len(self.matches)} partidos, {len(self.team_stats)} equipos con estadisticas")

    def _extract_stats(self, stats_list):
        result = {}
        for block in stats_list:
            if block.get('period') != 'ALL':
                continue
            for group in block.get('groups', []):
                for item in group.get('statisticsItems', []):
                    result[item['key']] = {'home': item.get('homeValue', 0), 'away': item.get('awayValue', 0)}
        return result

    # ─── COMPUTAR ESTADÍSTICAS ─────────────────────────
    def _compute_team_stats(self):
        team_raw = defaultdict(list)
        all_opponents = set()

        for m in self.matches:
            h, a = m['home_team'], m['away_team']
            hs = m.get('home_score', 0) or 0
            aws = m.get('away_score', 0) or 0
            if not m.get('statistics'):
                continue
            stats = self._extract_stats(m['statistics'])
            if not stats:
                continue

            team_raw[h].append({
                'stats': {k: v['home'] for k, v in stats.items()},
                'goals_for': hs, 'goals_against': aws,
                'home': True, 'result': 'W' if hs > aws else ('D' if hs == aws else 'L'),
                'opponent': a,
            })
            team_raw[a].append({
                'stats': {k: v['away'] for k, v in stats.items()},
                'goals_for': aws, 'goals_against': hs,
                'home': False, 'result': 'W' if aws > hs else ('D' if aws == hs else 'L'),
                'opponent': h,
            })

        # P1: promedios CRUDOS por equipo (sin ajustar)
        for team, games in team_raw.items():
            all_keys = set()
            for g in games:
                all_keys.update(g['stats'].keys())

            avg_stats = {}
            for key in all_keys:
                vals = [g['stats'].get(key, 0) for g in games]
                avg_stats[key] = sum(vals) / len(vals)

            gf = [g['goals_for'] for g in games]
            ga = [g['goals_against'] for g in games]
            wins = sum(1 for g in games if g['result'] == 'W')
            draws = sum(1 for g in games if g['result'] == 'D')

            self.team_stats[team] = {
                'games': len(games),
                'avg_stats_raw': avg_stats,
                'avg_goals_for': sum(gf) / len(gf),
                'avg_goals_against': sum(ga) / len(ga),
                'goals_for': sum(gf), 'goals_against': sum(ga),
                'wins': wins, 'draws': draws,
                'losses': len(games) - wins - draws,
                'results': [g['result'] for g in games],
                'opponents': [g['opponent'] for g in games],
            }
            self.team_matches[team] = games

        # P2: qué PERMITE cada equipo al rival (defensa)
        for m in self.matches:
            if not m.get('statistics'):
                continue
            stats = self._extract_stats(m['statistics'])
            if not stats:
                continue
            h, a = m['home_team'], m['away_team']
            hs = m.get('home_score', 0) or 0
            aws = m.get('away_score', 0) or 0
            # Lo que permite el equipo A al rival (home): las stats del visitante
            for key, vals in stats.items():
                if vals['away'] > 0:
                    self.team_allows[h][key].append(vals['away'])
                if vals['home'] > 0:
                    self.team_allows[a][key].append(vals['home'])
            # Lo que permite en goles
            self.team_allows[h]['goals'].append(aws)
            self.team_allows[a]['goals'].append(hs)

        # Calcular promedios de lo que PERMITE cada equipo
        for team in self.team_stats:
            avg_allows = {}
            for key, vals in self.team_allows[team].items():
                avg_allows[key] = sum(vals) / len(vals) if vals else 0
            self.team_stats[team]['avg_allows'] = avg_allows

        # P3: promedios de lo que permite LA LIGA (todos los equipos)
        self.league_allows = {}
        for team, ts in self.team_stats.items():
            for key, val in ts.get('avg_allows', {}).items():
                self.league_allows.setdefault(key, []).append(val)
        for key, vals in self.league_allows.items():
            self.league_allows[key] = sum(vals) / len(vals) if vals else 1

        # P4: ESTADÍSTICAS AJUSTADAS POR RIVAL
        for team, ts in self.team_stats.items():
            games = self.team_matches[team]
            adjusted = defaultdict(list)
            adjusted_gf = []
            adjusted_ga = []

            for g in games:
                opp = g['opponent']
                opp_allows = self.team_stats.get(opp, {}).get('avg_allows', {})
                league_avg = self.league_allows

                # Para cada stat: ratio = valor_conseguido / lo que permite el rival
                for key, val in g['stats'].items():
                    allowed = opp_allows.get(key, league_avg.get(key, 1))
                    if allowed and allowed > 0:
                        ratio = val / allowed
                    else:
                        ratio = 1.0
                    adjusted[key].append(ratio)

                # Goles ajustados
                opp_ga_allowed = opp_allows.get('goals', 1)
                if opp_ga_allowed > 0:
                    adjusted_gf.append(g['goals_for'] / opp_ga_allowed)
                else:
                    adjusted_gf.append(g['goals_for'])
                adjusted_ga.append(g['goals_against'])

            # Promedios ajustados
            avg_adj = {}
            for key, ratios in adjusted.items():
                avg_adj[key] = sum(ratios) / len(ratios) if ratios else 1.0
            # FIX: Para mercados absolutos (córners, tarjetas, faltas) usar el RAW,
            # no el ratio ajustado por rival. Esos stats no representan fuerza del equipo.
            ABSOLUTE_STATS = ['cornerKicks', 'yellowCards', 'redCards', 'fouls',
                              'fouledFinalThird', 'throwIns', 'totalShotsOnGoal',
                              'shotsOnTarget', 'shotsOnGoal', 'shotsOffGoal']
            for k in ABSOLUTE_STATS:
                if k in avg_adj:
                    avg_adj[k] = ts.get('avg_stats_raw', {}).get(k, avg_adj[k])

            ts['avg_stats'] = avg_adj               # ← ESTO ES LO QUE USA EL MODELO AHORA
            ts['avg_gf_adj'] = sum(adjusted_gf) / len(adjusted_gf) if adjusted_gf else ts['avg_goals_for']
            ts['avg_ga_adj'] = sum(adjusted_ga) / len(adjusted_ga) if adjusted_ga else ts['avg_goals_against']

            # Guardar también los raw para mostrar en la web
            ts['avg_stats_raw'] = ts.pop('avg_stats_raw')

    # ─── ELO ───────────────────────────────────────────
    def _compute_elo(self):
        for team in self.team_stats:
            self.elo[team] = 1500

        sorted_matches = sorted(
            [m for m in self.matches if m.get('statistics')],
            key=lambda m: m.get('start_timestamp', 0)
        )
        elo_history = {}

        for m in sorted_matches:
            h, a = m['home_team'], m['away_team']
            hs = m.get('home_score', 0) or 0
            aws = m.get('away_score', 0) or 0
            if h not in self.elo or a not in self.elo:
                continue

            round_name = m.get('round', '')
            is_ko = any(k in str(round_name).lower() for k in ['r32', 'r16', 'quarter', 'semi', 'final'])
            k_mult = 1.5 if is_ko else 1.0

            elo_h = self.elo[h] + ELO_HOME
            elo_a = self.elo[a]
            exp_h = 1 / (1 + 10 ** ((elo_a - elo_h) / 400))

            if hs > aws: actual_h, actual_a = 1, 0
            elif hs == aws: actual_h, actual_a = 0.5, 0.5
            else: actual_h, actual_a = 0, 1

            gd = abs(hs - aws)
            margin_mult = math.log(gd + 1, 2) if gd > 0 else 1
            k = ELO_K * k_mult * margin_mult

            self.elo[h] += k * (actual_h - exp_h)
            self.elo[a] += k * (actual_a - (1 - exp_h))
            elo_history.setdefault(h, []).append(self.elo[h])
            elo_history.setdefault(a, []).append(self.elo[a])

        for team in self.team_stats:
            history = elo_history.get(team, [])
            self.team_stats[team]['elo_momentum'] = history[-1] - history[-2] if len(history) >= 2 else 0
            self.team_stats[team]['elo'] = self.elo[team]

    # ─── PREDECIR PARTIDO ─────────────────────────────
    def predict_match(self, home_team, away_team):
        if home_team not in self.team_stats or away_team not in self.team_stats:
            missing = home_team if home_team not in self.team_stats else away_team
            return {'error': f'Equipo no encontrado: {missing}', 'home_team': home_team, 'away_team': away_team}

        ht = self.team_stats[home_team]
        at = self.team_stats[away_team]

        # ===== 1. MODELO ESTADÍSTICO → H/D/A =====
        stat_contributions = []
        for key, weight in WEIGHTS.items():
            hv = ht['avg_stats'].get(key, 1.0)
            av = at['avg_stats'].get(key, 1.0)
            if weight < 0:
                norm_diff = (av - hv) / max(abs(max(hv, av, 0.001)), 0.001) * 0.5
                contribution = norm_diff * abs(weight)
            else:
                norm_diff = (hv - av) / max(abs(max(hv, av, 0.001)), 0.001) * 0.5
                contribution = norm_diff * weight
            stat_contributions.append({
                'key': key, 'home': round(hv, 2), 'away': round(av, 2),
                'norm_diff': round(norm_diff, 3),
                'diff_pct': round((hv - av) / max(av, 0.001) * 100, 1),
                'weight': weight, 'contribution': round(contribution, 3),
            })

        stat_score = sum(c['contribution'] for c in stat_contributions) / max(len(stat_contributions), 1)
        stat_contributions.sort(key=lambda x: abs(x['contribution']), reverse=True)

        # Probabilidades del modelo estadístico: sigmoide asimétrica + campana para draw
        # stat_score > 0 → home favorito, < 0 → away favorito
        stat_home_raw = (math.tanh(stat_score * 0.8) + 1) / 2  # 0..1
        # Draw: campana gaussiana centrada en 0 (más draw cuando equipos igualados)
        stat_draw_raw = STAT_DRAW_PEAK * math.exp(-(stat_score ** 2) / STAT_DRAW_WIDTH)
        # Away: el resto, pero aseguramos que no sea negativo
        stat_away_raw = max(0.02, 1 - stat_home_raw - stat_draw_raw)
        # Si el draw es tan alto que away queda negativo, reescalamos home
        if stat_home_raw + stat_draw_raw > 0.98:
            excess = stat_home_raw + stat_draw_raw - 0.98
            stat_home_raw -= excess * 0.7
            stat_draw_raw -= excess * 0.3
            stat_away_raw = 0.02
        # Normalizar
        total_s = stat_home_raw + stat_draw_raw + stat_away_raw
        s_home = stat_home_raw / total_s
        s_draw = stat_draw_raw / total_s
        s_away = stat_away_raw / total_s

        # ===== 2. ELO → H/D/A =====
        elo_diff = (self.elo[home_team] + ELO_HOME) - self.elo[away_team]
        elo_home = 1 / (1 + 10 ** (-elo_diff / 400))
        # Draw: inversamente proporcional a diferencia de Elo
        draw_factor = 1 - abs(elo_diff) / DRAW_MARGIN
        elo_draw_raw = max(0.08, draw_factor * 0.28)
        elo_away = (1 - elo_home - elo_draw_raw) * (1 - elo_draw_raw / 0.28) + elo_draw_raw * 0.5
        elo_away = max(0.05, min(elo_away, 1 - elo_home - elo_draw_raw))
        total_e = elo_home + elo_draw_raw + elo_away
        e_home = elo_home / total_e
        e_draw = elo_draw_raw / total_e
        e_away = elo_away / total_e

        # ===== 3. POISSON → H/D/A (ya es nativo) =====
        h_gf = ht['avg_goals_for']
        h_ga = ht['avg_goals_against']
        a_gf = at['avg_goals_for']
        a_ga = at['avg_goals_against']
        exp_hg = (h_gf + a_ga) / 2
        exp_ag = (a_gf + h_ga) / 2

        p_home_raw = p_draw_raw = p_away_raw = 0
        for hg in range(8):
            for ag in range(8):
                prob = (math.exp(-exp_hg) * exp_hg**hg / math.factorial(hg) *
                        math.exp(-exp_ag) * exp_ag**ag / math.factorial(ag))
                if hg > ag: p_home_raw += prob
                elif hg == ag: p_draw_raw += prob
                else: p_away_raw += prob
        total_p = p_home_raw + p_draw_raw + p_away_raw
        p_home = p_home_raw / total_p
        p_draw = p_draw_raw / total_p
        p_away = p_away_raw / total_p

        # ===== 4. FORMA → H/D/A =====
        h_form = sum(3 if r == 'W' else 1 if r == 'D' else 0 for r in ht['results'][-3:])
        a_form = sum(3 if r == 'W' else 1 if r == 'D' else 0 for r in at['results'][-3:])
        h_draws = sum(1 for r in ht['results'][-3:] if r == 'D')
        a_draws = sum(1 for r in at['results'][-3:] if r == 'D')
        form_draw_raw = 0.25 + (h_draws + a_draws) / 12
        total_form = h_form + a_form + 3  # +3 para evitar división por 0
        f_home = (h_form + 1) / total_form
        f_draw = form_draw_raw
        f_away = (a_form + 1) / total_form
        total_f = f_home + f_draw + f_away
        f_home /= total_f
        f_draw /= total_f
        f_away /= total_f

        # ===== 5. MEZCLA FINAL (tridimensional H/D/A) =====
        comp_h = s_home * W_STATS + e_home * W_ELO + p_home * W_POISSON + f_home * W_FORM
        comp_d = s_draw * W_STATS + e_draw * W_ELO + p_draw * W_POISSON + f_draw * W_FORM
        comp_a = s_away * W_STATS + e_away * W_ELO + p_away * W_POISSON + f_away * W_FORM

        total_comp = comp_h + comp_d + comp_a
        comp_h /= total_comp
        comp_d /= total_comp
        comp_a /= total_comp

        # Predicción
        mx = max(comp_h, comp_d, comp_a)
        if mx == comp_h: pred = 'HOME'
        elif mx == comp_d: pred = 'DRAW'
        else: pred = 'AWAY'

        if mx > 0.55: conf = 'ALTA'
        elif mx > 0.40: conf = 'MEDIA'
        else: conf = 'BAJA'

        # Narrativa
        narr = self._generate_narrative(home_team, away_team, ht, at, stat_contributions,
                                         h_gf, h_ga, a_gf, a_ga, elo_diff, conf)

        return {
            'home_team': home_team, 'away_team': away_team,
            'prediction': pred, 'confidence': conf,
            'probabilities': {
                'home': round(comp_h * 100, 1),
                'draw': round(comp_d * 100, 1),
                'away': round(comp_a * 100, 1),
            },
            'expected_goals': {'home': round(exp_hg, 2), 'away': round(exp_ag, 2)},
            'elo': {'home': round(self.elo[home_team]), 'away': round(self.elo[away_team]), 'diff': round(elo_diff)},
            'team_stats': {'home': ht, 'away': at},
            'top_stats': stat_contributions[:8],
            'narrative': narr,
            'model_breakdown': {
                'elo': round(e_home * 100, 1),
                'statistical': round(s_home * 100, 1),
                'poisson': round(p_home * 100, 1),
            },
        }

    # ─── NARRATIVA ─────────────────────────────────────
    def _generate_narrative(self, h_team, a_team, ht, at, top_stats, h_gf, h_ga, a_gf, a_ga, elo_diff, conf):
        parts = []
        if elo_diff > 50:
            parts.append(f"Elo favorece claramente a {h_team} (+{round(elo_diff)})")
        elif elo_diff > 0:
            parts.append(f"Elo ligeramente a favor de {h_team} (+{round(elo_diff)})")
        elif elo_diff > -50:
            parts.append(f"Elo ligeramente a favor de {a_team} (+{abs(round(elo_diff))})")
        else:
            parts.append(f"Elo favorece claramente a {a_team} (+{abs(round(elo_diff))})")
        parts.append(f"{h_team} marca {h_gf:.1f} goles/partido y encaja {h_ga:.1f}")
        parts.append(f"{a_team} marca {a_gf:.1f} goles/partido y encaja {a_ga:.1f}")
        if top_stats:
            s = top_stats[0]
            stat_name = self._stat_label(s['key'])
            if s['diff_pct'] > 10:
                parts.append(f"{h_team} domina en {stat_name} (+{s['diff_pct']}%)")
            elif s['diff_pct'] > 0:
                parts.append(f"Ligera ventaja de {h_team} en {stat_name}")
            elif s['diff_pct'] < -10:
                parts.append(f"{a_team} domina en {stat_name} (+{abs(s['diff_pct'])}%)")
            else:
                parts.append(f"Ligera ventaja de {a_team} en {stat_name}")
        h_form = ''.join(ht['results'][-3:]) if len(ht['results']) >= 3 else ''.join(ht['results'])
        a_form = ''.join(at['results'][-3:]) if len(at['results']) >= 3 else ''.join(at['results'])
        parts.append(f"Forma: {h_team} [{h_form}] | {a_team} [{a_form}]")
        h_mom = ht.get('elo_momentum', 0)
        a_mom = at.get('elo_momentum', 0)
        if h_mom > 5 and a_mom < -5:
            parts.append(f"Momento favorable a {h_team}")
        elif a_mom > 5 and h_mom < -5:
            parts.append(f"Momento favorable a {a_team}")
        return ' | '.join(parts)

    def _stat_label(self, key):
        labels = {
            'expectedGoals': 'xG (goles esperados)', 'bigChanceCreated': 'ocasiones claras',
            'totalShotsOnGoal': 'tiros totales', 'shotsOnTarget': 'tiros a puerta',
            'ballPossession': 'posesión', 'cornerKicks': 'córners',
            'passes': 'pases', 'touchesInPenaltyArea': 'toques en área',
            'finalThirdEntries': 'entradas último tercio', 'crosses': 'centros',
            'goalkeeperSaves': 'paradas del portero', 'fouls': 'faltas',
            'yellowCards': 'tarjetas amarillas',
            'errorsLeadToGoal': 'errores que terminan en gol',
        }
        return labels.get(key, key)

    def get_today_matches(self, date_str='2026-06-29'):
        import requests
        from datetime import datetime
        url = "https://api.sofascore.com/api/v1/unique-tournament/16/season/58210/events/next/0"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        events = resp.json().get('events', [])
        today = []
        for e in events:
            ts = e.get('startTimestamp', 0)
            dt = datetime.fromtimestamp(ts)
            if dt.strftime('%Y-%m-%d') == date_str:
                today.append({
                    'id': e.get('id'),
                    'home_team': e.get('homeTeam', {}).get('name'),
                    'away_team': e.get('awayTeam', {}).get('name'),
                    'time': dt.strftime('%H:%M'),
                    'round': e.get('roundInfo', {}).get('round'),
                })
        return today
