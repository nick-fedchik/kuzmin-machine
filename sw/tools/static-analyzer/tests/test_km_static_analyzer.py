#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматизовані тести статичного аналізатора Машини Кузьміна (test_km_static_analyzer.py).
Перевіряє алгоритм Тар'яна, виявлення станів гонитви Бернштейна, детекцію мертвих
ітераторів та коректність розрахунку WCET за формулою Грехема — Брента.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from km_static_analyzer import (
    DiagnosticReport,
    KuzminStaticAnalyzer,
    ParallelStmtInfo,
    SubscriptionEdge,
)


class TestKuzminStaticAnalyzer(unittest.TestCase):
    """Набір модульних тестів для km_static_analyzer."""

    def setUp(self) -> None:
        self.analyzer = KuzminStaticAnalyzer(num_fpga_cores=8, clock_mhz=100.0)

    def test_dag_cascade_no_cycles(self) -> None:
        """Перевірка ациклічного графа подій (DAG): відсутність помилок Livelock."""
        self.analyzer.add_edge(SubscriptionEdge("A", "B", "POST •", "B = A * 2", exec_cycles=4))
        self.analyzer.add_edge(SubscriptionEdge("B", "C", "PRE ←", "C = B + 1", exec_cycles=5))
        self.analyzer.check_livelock_cycles()

        error_codes = [d.code for d in self.analyzer.diagnostics if d.severity == "ERROR"]
        self.assertEqual(error_codes, [], "В ациклічному графі не повинно бути помилок циклів")

    def test_unbounded_livelock_detected(self) -> None:
        """Перевірка виявлення нескінченного циклу (KM-E001) між двома концептами."""
        self.analyzer.add_edge(SubscriptionEdge("Ping", "Pong", ":: ~", "Pong = Ping + 1", exec_cycles=3))
        self.analyzer.add_edge(SubscriptionEdge("Pong", "Ping", ":: ~", "Ping = Pong + 1", exec_cycles=3))
        self.analyzer.check_livelock_cycles()

        e001_reports = [d for d in self.analyzer.diagnostics if d.code == "KM-E001"]
        self.assertEqual(len(e001_reports), 1, "Має бути виявлено рівно один нескінченний реактивний шторм")
        self.assertIn("Ping", e001_reports[0].message)
        self.assertIn("Pong", e001_reports[0].message)

    def test_bounded_cycle_with_monotone_variant_accepted(self) -> None:
        """Перевірка безпечного спадного циклу (KM-I001) із доведеною спадною функцією."""
        self.analyzer.add_edge(
            SubscriptionEdge(
                "Count", "Count", "{[ _ ~ ] < 10}", "Count += 1",
                exec_cycles=4, max_bound_iterations=10, has_monotone_variant=True
            )
        )
        self.analyzer.check_livelock_cycles()

        error_codes = [d.code for d in self.analyzer.diagnostics if d.severity == "ERROR"]
        self.assertEqual(error_codes, [], "Обмежений цикл не повинен викликати помилок")
        info_codes = [d.code for d in self.analyzer.diagnostics if d.code == "KM-I001"]
        self.assertEqual(len(info_codes), 1, "Повинно бути інформаційне повідомлення про безпечний цикл")

    def test_dead_loop_iterator_missing_initial_state(self) -> None:
        """Перевірка детекції забутого початкового токена '_' (KM-W003)."""
        self.analyzer.add_edge(SubscriptionEdge("i", "i", "{~ < 10}", "i += 1", exec_cycles=4))
        self.analyzer.check_dead_loop_iterators()

        w003_reports = [d for d in self.analyzer.diagnostics if d.code == "KM-W003"]
        self.assertEqual(len(w003_reports), 1, "Має бути попередження про пропущений токен '_'")
        self.assertIn("Нульова ітерація може не запуститися", w003_reports[0].message)

    def test_dead_loop_iterator_with_initial_state_ok(self) -> None:
        """Перевірка правильного циклу з токеном '_': відсутність попередження KM-W003."""
        self.analyzer.add_edge(SubscriptionEdge("i", "i", "{[ _ ~ ] < 10}", "i += 1", exec_cycles=4))
        self.analyzer.check_dead_loop_iterators()

        w003_reports = [d for d in self.analyzer.diagnostics if d.code == "KM-W003"]
        self.assertEqual(len(w003_reports), 0, "Коректний предикат не повинен викликати попереджень")

    def test_bernstein_data_race_raw_detected(self) -> None:
        """Перевірка виявлення Read-After-Write (RAW) гонитви без Великої крапки."""
        stmts = [
            ParallelStmtInfo("Val += 5", phase_index=0, read_concepts={"Val"}, write_concepts={"Val"}),
            ParallelStmtInfo("Out = Val * 2", phase_index=0, read_concepts={"Val"}, write_concepts={"Out"}),
        ]
        self.analyzer.check_bernstein_data_races(hook_owner="SensorBlock", stmts=stmts)

        e002_reports = [d for d in self.analyzer.diagnostics if d.code == "KM-E002"]
        self.assertEqual(len(e002_reports), 1, "Має бути виявлено конфлікт RAW гонитви")
        self.assertIn("RAW Data Race", e002_reports[0].message)
        self.assertIn("Val", e002_reports[0].message)

    def test_bernstein_data_race_waw_detected(self) -> None:
        """Перевірка виявлення Write-After-Write (WAW) гонитви двох паралельних записів."""
        stmts = [
            ParallelStmtInfo("Status = 1", phase_index=0, read_concepts=set(), write_concepts={"Status"}),
            ParallelStmtInfo("Status = 2", phase_index=0, read_concepts=set(), write_concepts={"Status"}),
        ]
        self.analyzer.check_bernstein_data_races(hook_owner="AlarmBlock", stmts=stmts)

        e002_reports = [d for d in self.analyzer.diagnostics if d.code == "KM-E002"]
        self.assertEqual(len(e002_reports), 1, "Має бути виявлено конфлікт WAW гонитви")
        self.assertIn("WAW Data Race", e002_reports[0].message)

    def test_bernstein_race_eliminated_by_big_dot(self) -> None:
        """Перевірка усунення гонитви за допомогою Великої крапки (роздільні фази 0 та 1)."""
        stmts = [
            ParallelStmtInfo("Val += 5", phase_index=0, read_concepts={"Val"}, write_concepts={"Val"}),
            ParallelStmtInfo("Out = Val * 2", phase_index=1, read_concepts={"Val"}, write_concepts={"Out"}),
        ]
        self.analyzer.check_bernstein_data_races(hook_owner="SafeBlock", stmts=stmts)

        e002_reports = [d for d in self.analyzer.diagnostics if d.code == "KM-E002"]
        self.assertEqual(len(e002_reports), 0, "Велика крапка '•' усуває гонитву рознесенням у часі")

    def test_wcet_calculation_bounds(self) -> None:
        """Перевірка розрахунку WCET: T_1 > 0, T_inf <= WCET <= T_1 + overhead."""
        self.analyzer.add_edge(SubscriptionEdge("A", "B", "POST •", "B = A", exec_cycles=10))
        self.analyzer.add_edge(SubscriptionEdge("B", "C", "PRE ←", "C = B", exec_cycles=20))
        t1, wcet_cyc, wcet_us = self.analyzer.compute_wcet()

        self.assertEqual(t1, 30, "Сумарна робота T_1 має дорівнювати 30 тактам")
        self.assertGreater(wcet_cyc, 0, "WCET у тактах має бути додатнім")
        self.assertGreater(wcet_us, 0.0, "WCET у мікросекундах має бути додатнім")
        self.assertAlmostEqual(wcet_us, wcet_cyc / 100.0, places=4, msg="WCET_us = WCET_cyc / Clock_MHz")


if __name__ == "__main__":
    unittest.main()
