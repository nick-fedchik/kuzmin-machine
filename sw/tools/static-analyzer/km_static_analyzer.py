#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Статичний аналізатор графа підписок, верифікатор зупинки каскадів (Termination Checker),
детектор станів гонитви (Bernstein Data-Race Detector) та калькулятор WCET Машини Кузьміна
(km_static_analyzer.py).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# ============================================================================
# 1. СТРУКТУРИ ДАНИХ ДЛЯ АНАЛІЗУ ГРАФА ПОДІЙ ТА ПІДПИСОК (EDG)
# ============================================================================

@dataclass
class ParallelStmtInfo:
    """Опис елементарного оператора всередині підписки для перевірки умов Бернштейна."""
    stmt_text: str
    phase_index: int  # 0 = до крапки '•' (w1), 1 = після крапки '•' (w2)
    read_concepts: Set[str]
    write_concepts: Set[str]
    is_silent_reset: bool = False


@dataclass
class SubscriptionEdge:
    """Орієнтоване ребро каскаду в графі залежностей подій EDG."""
    source_concept: str
    target_concept: str
    event_predicate: str          # Напр. ":: ~", "= 10", "{[ _ ~ ] < N}", "> b"
    action_summary: str           # Напр. "Speed = dx * 10", "i += 1", "a -= b"
    exec_cycles: int = 4          # Тактова вартість виконання лінії O на ядрі PE
    max_bound_iterations: Optional[int] = None  # Верхня межа ітерацій (якщо цикл обмежений)
    has_monotone_variant: bool = False          # Наявність спадної функції рангу V


@dataclass
class DiagnosticReport:
    code: str
    severity: str  # "ERROR", "WARNING", "INFO"
    message: str
    remediation: str


# ============================================================================
# 2. ЯДРО СТАТИЧНОГО АНАЛІЗАТОРА МАШИНИ КУЗЬМІНА
# ============================================================================

class KuzminStaticAnalyzer:
    """
    Виконує 4 статичні перевірки скомпільованого модуля Машини Кузьміна:
    1) Виявлення необмежених циклів Livelock за алгоритмом Тар'яна + перевірка варіантів;
    2) Виявлення мертвих ітераторів (пропущений токен '_' у предикаті циклу);
    3) Виявлення станів гонитви (RAW / WAW / WAR) у паралельних групах без '•';
    4) Розрахунок гарантованого WCET у тактах і мікросекундах для FPGA PYNQ-Z1 (100 МГц).
    """

    def __init__(self, num_fpga_cores: int = 8, clock_mhz: float = 100.0) -> None:
        self.num_fpga_cores = num_fpga_cores
        self.clock_mhz = clock_mhz
        self.nodes: Set[str] = set()
        self.edges: List[SubscriptionEdge] = []
        self.diagnostics: List[DiagnosticReport] = []

    def add_edge(self, edge: SubscriptionEdge) -> None:
        self.nodes.add(edge.source_concept)
        self.nodes.add(edge.target_concept)
        self.edges.append(edge)

    def check_dead_loop_iterators(self) -> None:
        """Перевіряє, чи не забув розробник токен початкового стану '_' у циклі з '~'."""
        for e in self.edges:
            if e.source_concept == e.target_concept and "~" in e.event_predicate and "<" in e.event_predicate:
                if "_" not in e.event_predicate:
                    self.diagnostics.append(
                        DiagnosticReport(
                            code="KM-W003",
                            severity="WARNING",
                            message=(
                                f"Концепт-ітератор '{e.source_concept}' має предикат '{e.event_predicate}' "
                                f"без токена початкового стану '_'. Нульова ітерація може не запуститися!"
                            ),
                            remediation=f"Замініть умову на комбіновану подію: {{[ _ ~ ] {e.event_predicate}}}",
                        )
                    )

    def check_bernstein_data_races(self, hook_owner: str, stmts: List[ParallelStmtInfo]) -> None:
        """
        Перевіряє умови Бернштейна (RAW, WAW, WAR) для всіх операторів,
        що опинилися в одній фазі Великої крапки (однаковий phase_index).
        """
        n = len(stmts)
        for i in range(n):
            for j in range(i + 1, n):
                s1, s2 = stmts[i], stmts[j]
                if s1.phase_index != s2.phase_index:
                    continue  # Розділені оператором Великої крапки '•' -> виконуються послідовно!

                waw = s1.write_concepts & s2.write_concepts
                raw = s1.write_concepts & s2.read_concepts
                war = s1.read_concepts & s2.write_concepts
                conflicts = waw | raw | war

                if conflicts:
                    hazard_kind = "WAW" if waw else ("RAW" if raw else "WAR")
                    self.diagnostics.append(
                        DiagnosticReport(
                            code="KM-E002",
                            severity="ERROR",
                            message=(
                                f"Виявлено стан гонитви ({hazard_kind} Data Race) у підписці концепту "
                                f"'{hook_owner}' за концепт(и) {sorted(conflicts)} між паралельними "
                                f"операторами '{s1.stmt_text}' та '{s2.stmt_text}'!"
                            ),
                            remediation=(
                                f"Розділіть ці оператори фазовим оператором Великої крапки '•': "
                                f"{s1.stmt_text}  •  {{ {s2.stmt_text} }}"
                            ),
                        )
                    )

    def check_livelock_cycles(self) -> List[List[str]]:
        """
        Знаходить усі компоненти сильної зв'язності (SCC) за алгоритмом Тар'яна
        та перевіряє кожен нетривіальний цикл на наявність спадної функції рангу.
        """
        adj: Dict[str, List[SubscriptionEdge]] = {u: [] for u in self.nodes}
        for e in self.edges:
            adj[e.source_concept].append(e)

        index = 0
        indices: Dict[str, int] = {}
        lowlink: Dict[str, int] = {}
        stack: List[str] = []
        on_stack: Set[str] = set()
        sccs: List[List[str]] = []

        def strongconnect(u: str) -> None:
            nonlocal index
            indices[u] = index
            lowlink[u] = index
            index += 1
            stack.append(u)
            on_stack.add(u)

            for edge in adj.get(u, []):
                v = edge.target_concept
                if v not in indices:
                    strongconnect(v)
                    lowlink[u] = min(lowlink[u], lowlink[v])
                elif v in on_stack:
                    lowlink[u] = min(lowlink[u], indices[v])

            if lowlink[u] == indices[u]:
                comp: List[str] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    comp.append(w)
                    if w == u:
                        break
                sccs.append(comp)

        for node in sorted(self.nodes):
            if node not in indices:
                strongconnect(node)

        for comp in sccs:
            comp_set = set(comp)
            internal_edges = [
                e for e in self.edges
                if e.source_concept in comp_set and e.target_concept in comp_set
            ]
            if not internal_edges:
                continue

            # Перевіряємо, чи всі ребра циклу мають доведений монотонно спадний варіант
            all_bounded = all(
                e.has_monotone_variant or (e.max_bound_iterations is not None)
                for e in internal_edges
            )
            if not all_bounded:
                cycle_str = " -> ".join(comp + [comp[0]])
                self.diagnostics.append(
                    DiagnosticReport(
                        code="KM-E001",
                        severity="ERROR",
                        message=(
                            f"Виявлено потенційний нескінченний реактивний шторм (Event Livelock) "
                            f"у циклі концептів: [{cycle_str}] без спадної функції рангу!"
                        ),
                        remediation=(
                            "Додайте обмежувальний предикат події (напр. '< Max', '= 10'), "
                            "використайте тихе скидання ('= _ 0') або інструкцію 'Exit'."
                        ),
                    )
                )
            else:
                self.diagnostics.append(
                    DiagnosticReport(
                        code="KM-I001",
                        severity="INFO",
                        message=(
                            f"Верифіковано безпечний конвергентний цикл {comp}: "
                            f"існує строго спадна функція рангу V(Σ)."
                        ),
                        remediation="Дій не потребує (гарантована зупинка за скінченне число кроків).",
                    )
                )
        return sccs

    def compute_wcet(self) -> Tuple[int, int, float]:
        """
        Обчислює сумарну роботу T_1, критичний шлях T_inf та верхню оцінку WCET
        за формулою Грехема — Брента для P ядер FPGA.
        Повертає (T_1_cycles, WCET_cycles, WCET_microseconds).
        """
        t1_work = 0
        t_inf_crit = 0
        for e in self.edges:
            iters = e.max_bound_iterations if e.max_bound_iterations is not None else 1
            cost = iters * e.exec_cycles
            t1_work += cost
            t_inf_crit += cost  # Консервативна верхня межа критичного шляху

        by_src: Dict[str, List[int]] = {}
        for e in self.edges:
            iters = e.max_bound_iterations if e.max_bound_iterations is not None else 1
            by_src.setdefault(e.source_concept, []).append(iters * e.exec_cycles)

        t_inf_refined = sum(max(costs) for costs in by_src.values())
        dispatch_overhead = len(by_src) * 2
        wcet_cycles = int(
            t_inf_refined
            + max(0, t1_work - t_inf_refined) / self.num_fpga_cores
            + dispatch_overhead
        )
        wcet_us = wcet_cycles / self.clock_mhz
        return t1_work, wcet_cycles, wcet_us


# ============================================================================
# 3. ДЕМОНСТРАЦІЯ РОБОТИ СТАТИЧНОГО АНАЛІЗАТОРА
# ============================================================================

def main():
    print("=" * 84)
    print("СТАТИЧНИЙ АНАЛІЗАТОР ТА ВЕРИФІКАТОР ЗУПИНКИ КАСКАДІВ МАШИНИ КУЗЬМІНА")
    print("=" * 84)

    analyzer = KuzminStaticAnalyzer(num_fpga_cores=8, clock_mhz=100.0)

    # 1. Безпечний каскад одометра + паралельний контролер діапазону Value ~ [Up Down]
    analyzer.add_edge(SubscriptionEdge("Distance", "Speed", "POST •", "Speed = dx * 10", exec_cycles=5))
    analyzer.add_edge(SubscriptionEdge("Speed", "Accelleration", "PRE ←", "Accel = v - Speed", exec_cycles=6))
    analyzer.add_edge(SubscriptionEdge("Speed", "UpCheck", "~ [Up Down]", "Check < Up", exec_cycles=4))
    analyzer.add_edge(SubscriptionEdge("Speed", "DownCheck", "~ [Up Down]", "Check > Down", exec_cycles=4))

    # 2. Безпечний реактивний цикл ітератора масиву (i = 0 .. 15)
    analyzer.add_edge(
        SubscriptionEdge(
            "i", "i", "{[ _ ~ ] < 16}", "i += 1",
            exec_cycles=4, max_bound_iterations=16, has_monotone_variant=True
        )
    )

    # 3. Штучно внесений небезпечний цикл Livelock між концептами Ping та Pong
    analyzer.add_edge(SubscriptionEdge("Ping", "Pong", ":: ~", "Pong = Ping + 1", exec_cycles=3))
    analyzer.add_edge(SubscriptionEdge("Pong", "Ping", ":: ~", "Ping = Pong + 1", exec_cycles=3))

    # 4. Перевірка стану гонитви у паралельній групі без Великої крапки '•'
    analyzer.check_bernstein_data_races(
        hook_owner="BadOdometer",
        stmts=[
            ParallelStmtInfo("Distance += x", phase_index=0, read_concepts={"Distance", "x"}, write_concepts={"Distance"}),
            ParallelStmtInfo("Speed = Distance * 10", phase_index=0, read_concepts={"Distance"}, write_concepts={"Speed"}),
        ],
    )

    analyzer.check_livelock_cycles()
    analyzer.check_dead_loop_iterators()
    t1, wcet_cyc, wcet_us = analyzer.compute_wcet()

    for diag in analyzer.diagnostics:
        print(f"\n[{diag.severity}] {diag.code}: {diag.message}")
        print(f"  -> Рекомендація: {diag.remediation}")

    print("\n" + "-" * 84)
    print(f"Оцінка WCET каскаду (8 ядер PE @ 100 МГц): T_1 = {t1} тактів | WCET = {wcet_cyc} тактів ({wcet_us:.2f} мкс)")
    print("=" * 84)


if __name__ == "__main__":
    main()
